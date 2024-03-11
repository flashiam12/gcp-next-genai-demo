from google.cloud import storage

def list_folder_in_bucket(bucket_name, folder_name):
    # storage.Blob().public_url
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket_name)
    folders = bucket.list_blobs(prefix=folder_name)
    folders = list(map(lambda x: str(x.public_url).replace("https://", "gs://").replace("storage.googleapis.com/",""), folders))
    print(folders, len(folders))

list_folder_in_bucket("confluent-gcp-next-24", "raw-dataset/images")