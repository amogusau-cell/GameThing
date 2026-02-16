FROM python:3.11-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir fastapi uvicorn pydantic pyyaml requests tqdm python-multipart

EXPOSE 8000

CMD ["python3", "server.py"]
