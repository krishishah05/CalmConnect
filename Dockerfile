FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m textblob.download_corpora

COPY . .
RUN mkdir -p data

EXPOSE 5000

CMD ["python", "api/main.py"]
