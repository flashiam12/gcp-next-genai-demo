from cloud.ml.applied.images.image_to_text import image_to_attributes, image_to_product_description, get_image_bytes_from_url, get_url_from_gcs, from_gsc_uri
from cloud.ml.applied.model.domain_model import ImageRequest
from cloud.ml.applied.config import Config
from google.cloud import storage
from google.cloud import aiplatform
from google.protobuf import struct_pb2
from confluent_kafka import Producer, Consumer
import json
import base64
import typing
from pydantic import BaseModel
import logging
import time

logger = logging.Logger(name="gcp-genai-demo-datagen")

def list_images_in_bucket(bucket_name, folder_name):
    # storage.Blob().public_url
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket_name)
    folders = bucket.list_blobs(prefix=folder_name)
    image_list = list(map(lambda x: str(x.public_url).replace("https://", "gs://").replace("storage.googleapis.com/",""), folders))
    return image_list
    # print(folders, len(folders))

def load_image_bytes(image_uri:str):
    image_bytes = from_gsc_uri(image_uri)
    return image_bytes._image.data

def read_config():
  # reads the client configuration from client.properties
  # and returns it as a key-value map
  config = {}
  with open("app/client.properties") as fh:
    for line in fh:
      line = line.strip()
      if len(line) != 0 and line[0] != "#":
        parameter, value = line.strip().split('=', 1)
        config[parameter] = value.strip()
  return config

class EmbeddingResponse(typing.NamedTuple):
    text_embedding: typing.Sequence[float]
    image_embedding: typing.Sequence[float]

class EmbeddingPredictionClient:
    """Wrapper around Prediction Service Client."""

    def __init__(
        self,
        project: str,
        location: str = "us-central1",
        api_regional_endpoint: str = "us-central1-aiplatform.googleapis.com",
    ):
        client_options = {"api_endpoint": api_regional_endpoint}
        # Initialize client that will be used to create and send requests.
        # This client only needs to be created once, and can be reused for multiple requests.
        self.client = aiplatform.gapic.PredictionServiceClient(
            client_options=client_options
        )
        self.location = location
        self.project = project

    def get_embedding(self, text: str = None, image_uri: str = None):
        if not text and not image_uri:
            raise ValueError("At least one of text or image_file must be specified.")

        # Load image file
        image_bytes = None
        if image_uri:
            image_bytes = load_image_bytes(image_uri)

        instance = struct_pb2.Struct()
        if text:
            instance.fields["text"].string_value = text

        if image_bytes:
            encoded_content = base64.b64encode(image_bytes).decode("utf-8")
            image_struct = instance.fields["image"].struct_value
            image_struct.fields["bytesBase64Encoded"].string_value = encoded_content

        instances = [instance]
        endpoint = (
            f"projects/{self.project}/locations/{self.location}"
            "/publishers/google/models/multimodalembedding@001"
        )
        response = self.client.predict(endpoint=endpoint, instances=instances)

        text_embedding = None
        if text:
            text_emb_value = response.predictions[0]["textEmbedding"]
            text_embedding = [v for v in text_emb_value]

        image_embedding = None
        if image_bytes:
            image_emb_value = response.predictions[0]["imageEmbedding"]
            image_embedding = [v for v in image_emb_value]

        return EmbeddingResponse(
            text_embedding=text_embedding, image_embedding=image_embedding
        )

class ProductEvent(BaseModel):
    ProductId: int
    ProductImageGCSUri: str
    ProductDescription: str
    ProductAttributes: str

def run():

    images = list_images_in_bucket("confluent-gcp-next-24", "raw-dataset/images")
    i = 1000
    while len(images)>0:
        """"
        Creating the product description and product attributes from the gcs uri
        """
        try:
            t_s = time.time()
            image_uri = images[0]
            print(image_uri)
            request = ImageRequest(image=image_uri)
            result_att = image_to_attributes(request)
            result_desc = image_to_product_description(request.image)
            images.remove(image_uri)
            
            prod_event = ProductEvent(ProductId=i+1, ProductImageGCSUri=image_uri, ProductDescription=result_desc, ProductAttributes=json.dumps(result_att))
            
            config = read_config()
            topic = "gcp_genai_demo_context"
            # creates a new producer instance
            producer = Producer(config)

            # produces a sample message
            key = {"ProductId": prod_event.ProductId}
            value = prod_event.json()
            # print(value)
            producer.produce(topic, key=json.dumps(key), value=value)
            print("Key : {0}, Value: {1}, Topic: {2}".format(json.dumps(key), value, topic))
            # print(f"Produced message to topic {topic}: key = {key:12} value = {value:12}")
  
  # send any outstanding or buffered messages to the Kafka broker
            producer.flush()

            t_e = time.time()
            if 5>t_e-t_s>0:
                d = t_e - t_s
                # print(d)
                time.sleep(5-d)
            i = i + 1
        except Exception as e:
            print("An unknown error occured:{}".format(e))
        # print(json.dumps(result_att.dict()))
        # print(result_desc)

        # """"
        # Creating the embedding from the image
        # """
        # try:
        #     embedding_client = EmbeddingPredictionClient(
        #         project=Config.value(Config.SECTION_PROJECT, "id"), 
        #         location=Config.value(Config.SECTION_PROJECT, "location"), 
        #         api_regional_endpoint=Config.value(Config.SECTION_PROJECT, "endpoint")
        #         )
        #     response = embedding_client.get_embedding(text=json.dumps(result_att.dict())+result_desc, image_uri=image_uri)
        # except Exception as e:
        #     logger.error(e)
        # print(response.text_embedding)

if __name__=="__main__":
    run()
    # os.path.