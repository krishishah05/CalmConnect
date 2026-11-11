FROM python:3.11-slim

WORKDIR /app

# Timezone data, so setting TZ changes where day boundaries fall.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV CALMCONNECT_DATA_DIR=/app/data
EXPOSE 5000

# The app listens on all interfaces inside the container; docker-compose only
# publishes the port on localhost.
CMD ["python", "-m", "api.main"]
