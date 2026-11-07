FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Mount thư mục data từ ngoài: docker run -v ./data:/app/data ...
ENV CSV_PATH=/app/data \
    BATCH_SIZE=100

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
