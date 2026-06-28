# build v8
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dashboard_gradio.py .
COPY data/ ./data/

EXPOSE 10000

CMD ["python", "dashboard_gradio.py"]
