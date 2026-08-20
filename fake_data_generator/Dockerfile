FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir aiohttp websockets

COPY main.py .

CMD ["python", "main.py"]
