FROM python:3.11-slim-buster
WORKDIR /app
COPY . /app/
RUN apt-get update && apt-get install gcc python3-dev -y
RUN pip install -r requirements.local.txt
WORKDIR /app/google
CMD ["python", "app/main.py"]