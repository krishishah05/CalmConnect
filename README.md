# CalmConnect

A command-line mood tracker and journaling tool with a REST API backend. Log daily entries, get sentiment and emotion feedback, track your streak, and review weekly trends — all from the terminal or via HTTP.

Built with Python, Flask, SQLite, and [Rich](https://github.com/Textualize/rich).

---

## Features

- **Mood detection** — classifies each entry as positive, neutral, or negative using NLP
- **Emotion labeling** — identifies emotions like anxiety, sadness, happiness, and fatigue from entry text
- **Streak tracking** — counts consecutive days with at least one entry
- **Weekly summary** — average polarity and mood breakdown over the last 7 days
- **REST API** — submit entries and query logs/stats programmatically
- **SQLite storage** — no external database needed; data lives in a single local file
- **Docker support** — runs as a container with persistent volume mounting

---

## Setup

```bash
git clone https://github.com/krishishah05/CalmConnect
cd CalmConnect
pip install -r requirements.txt
python -m textblob.download_corpora
```

Copy the example env file if you want to customize paths:

```bash
cp .env.example .env
```

---

## CLI Usage

**Log an entry:**
```bash
python cli/main.py alice log "Had a productive morning, feeling really focused"
```
```
Entry saved. Mood: positive (polarity 0.43)
Detected emotions: happy
```

**View recent history:**
```bash
python cli/main.py alice history --limit 5
```

**View weekly stats and current streak:**
```bash
python cli/main.py alice stats
```
```
Weekly summary — alice
  Entries logged:   6
  Avg polarity:     0.18
  Negative         1
  Neutral          2
  Positive         3
  Current streak:  3 days
```

---

## API Usage

Start the development server:
```bash
python api/main.py
```

### Submit an entry

```bash
curl -X POST http://localhost:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "token": "secret123", "text": "Feeling calm and present today"}'
```

```json
{
  "user_id": "alice",
  "date": "2024-03-15",
  "text": "Feeling calm and present today",
  "mood": "positive",
  "polarity": 0.35,
  "emotions": ["happy"]
}
```

### Get logs

```bash
curl "http://localhost:5000/logs/alice?token=secret123"
curl "http://localhost:5000/logs/alice?token=secret123&limit=5"
```

### Get stats

```bash
curl "http://localhost:5000/stats/alice?token=secret123"
```

```json
{
  "weekly": {
    "entries": 6,
    "avg_polarity": 0.18,
    "mood_counts": {"positive": 3, "neutral": 2, "negative": 1}
  },
  "streak": 3
}
```

---

## Auth

By default, `test_user` / `secret123` is available for local development.

To add real users, create `data/tokens.json`:

```json
{
  "alice": "your_token_here",
  "bob": "another_token"
}
```

---

## Running Tests

```bash
python -m unittest discover tests
```

The test suite covers sentiment analysis, emotion detection, journal entry creation, SQLite storage, and all API endpoints using Flask's test client.

---

## Docker

```bash
docker-compose up --build
```

The API runs on `http://localhost:5000`. Journal data is persisted to `./data` on the host.
