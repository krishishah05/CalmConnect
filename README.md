# CalmConnect

CalmConnect started as a small personal project because I wanted somewhere to write down my thoughts at the end of the day. Over time it grew into a way to keep track of little moments, notice how I was feeling, and come back to experiences I didn't want to forget.

While studying abroad, I've especially enjoyed journaling about the places I've visited and the things I've experienced. When I look back on this semester, I want to remember more than photos and itineraries. I want to remember what those days actually felt like.

CalmConnect is a private journal you can use from the terminal or a browser. You write, it keeps your entries searchable, and it gives you a gentle look back at your week or at a whole trip. It isn't a therapist or a chatbot, and it doesn't try to tell you how you feel.

## What it does

- **Write, edit and delete entries**, each with an optional title, place and tags. You can backdate an entry if you missed a day.
- **Prompts** for when you don't know where to start.
- **Collections.** Tags like `morocco` or `copenhagen` group entries, so you can read a trip from start to finish and see how the tone of your writing changed along the way.
- **Search** across text, titles and places, and filter by tag or date range.
- **Weekly reflection**: tone per day, the overall mix, the feelings that came up most, how many days you wrote, and your current and longest streaks, summed up in a few plain sentences.
- **Looking back** shows an older entry, preferring one written on this day in an earlier year.

## How the analysis works

Each entry gets two separate readings:

- **Tone** (positive, neutral or negative) comes from [TextBlob](https://textblob.readthedocs.io/)'s polarity score, which runs from -1 to 1. Anything between -0.1 and 0.1 is neutral.
- **Feelings** (happy, calm, grateful, sad, anxious, angry, tired) come from a small word list in [`app/analysis.py`](app/analysis.py). Matching is on whole words and short phrases, so "unhappy" isn't happy and "downtown" isn't "down". A feeling is skipped when a negation ("not", "never", "don't" and so on) appears up to three words before it in the same clause. In "I wasn't sad, just tired", only *tired* counts.

The two can disagree on purpose: "Exhausted but proud of today" has a positive tone and still names *tired*. In weekly stats, each day's tone is the average of its entries, and every day counts equally, so one day with five entries doesn't outweigh the rest.

## Getting started

Requires Python 3.10 or newer.

```bash
git clone https://github.com/krishishah05/CalmConnect
cd CalmConnect
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

This installs Flask, TextBlob and Rich, and adds a `calmconnect` command. Your journal, a generated secret key and your CLI login are kept in `./data`, which git ignores. [`.env.example`](.env.example) lists the optional settings.

## The command line

```bash
calmconnect register
calmconnect journal                              # type freely, finish with Ctrl-D
calmconnect journal --prompt
calmconnect journal "Rainy day by the canal." --place Copenhagen --tags travel,copenhagen
calmconnect journal "Finally wrote about Saturday." --date 2026-11-07

calmconnect history --tag copenhagen --oldest    # read a trip in order
calmconnect history -s bakery                    # search text, titles and places
calmconnect history --on 2026-10-02
calmconnect show 12
calmconnect edit 12                              # opens $EDITOR
calmconnect edit 12 --tags travel,morocco
calmconnect delete 12

calmconnect reflect                              # your week, plus an older entry
calmconnect stats
calmconnect tags morocco
```

`calmconnect tags morocco` after a trip:

```
#morocco  4 entries, 2026-10-01 to 2026-10-06

 Oct 1     Oct 2     Oct 4     Oct 6
positive  positive  positive  negative
Your writing sounded more negative toward the end than at the start.
Feelings named most: grateful (2), anxious (1), calm (1)
```

Every command has `--help`. Without installing, `python -m cli.main` works from the project folder.

## The web app

```bash
flask --app api.main run
```

Open http://127.0.0.1:5000 and create an account. There are four pages, **Write**, **Journal**, **Collections** and **Reflect**, built with plain HTML and CSS and no JavaScript. They work on phones and follow your system's light or dark mode.

With Docker (data stays in `./data`, and the port is only opened on localhost):

```bash
docker compose up --build
```

## The JSON API

The same app serves a JSON API under `/api`. Get a token once, then send it as `Authorization: Bearer <token>`.

```bash
curl -X POST localhost:5000/api/tokens -H "Content-Type: application/json" \
     -d '{"username": "krishi", "password": "a long password"}'
```

| Route | Purpose |
| --- | --- |
| `POST /api/register` | Create an account (`username`, `password`) |
| `POST /api/tokens` | Log in; returns a token valid for 30 days |
| `DELETE /api/tokens/current` | Log out by revoking the token |
| `GET /api/entries` | List entries. Optional: `q`, `tag`, `from`, `to`, `order=newest\|oldest`, `limit` (1 to 100), `offset` |
| `POST /api/entries` | Create: `text`, plus optional `title`, `place`, `tags`, `date`, `prompt` |
| `GET`, `PATCH`, `DELETE /api/entries/<id>` | Read, change (any of `text`, `title`, `place`, `tags`, `date`) or delete one entry |
| `GET /api/tags` | Tags with entry counts and date ranges |
| `GET /api/tags/<tag>` | One collection: entries in order, timeline and tone summary |
| `GET /api/stats` | Weekly summary and streaks |
| `GET /api/revisit` | An older entry to look back on |

Errors come back as `{"error": "..."}`. Someone else's entry gets the same 404 as one that doesn't exist.

## Privacy and security

- Passwords are hashed with Werkzeug's scrypt. There are no built-in accounts.
- The web app, CLI and API all use the same kind of login token. The database stores only a SHA-256 hash of each token, tokens expire after 30 days, and logging out deletes them.
- Tokens never appear in URLs. The web app keeps its token in a signed HttpOnly cookie, and every form has a CSRF token.
- Every query that touches entries is limited to the logged-in user in the SQL itself.
- The `data` folder is created readable only by your OS user. The CLI has no way to act as another user without their password.
- The server runs without debug mode and listens on 127.0.0.1 unless told otherwise.

## Tests

```bash
python -m unittest discover tests
```

The tests cover the analysis edge cases, entry validation, search and filters, streaks and weekly stats around date boundaries, trip collections staying correct after edits and deletes, migrating an old database, authentication, keeping users apart, and the API, web pages and CLI end to end.

## Project layout

```
app/analysis.py   tone and feelings for a piece of text
app/auth.py       accounts, password hashing and login tokens
app/journal.py    validation and journal operations used by every interface
app/stats.py      streaks, weekly summaries and collection summaries
app/storage.py    SQLite schema and queries
api/main.py       Flask app setup and the JSON API
api/web.py        browser pages (templates/ and static/ sit next to it)
cli/main.py       the calmconnect command
tests/            one test file per area
```

## Limitations

- **The analysis only sees words.** It misses sarcasm, slang, emoji and most non-English writing, and anything outside the word list. TextBlob also scores some sentences oddly: "I don't feel anxious anymore" comes out slightly negative. The tone and feelings are a rough summary of the words, never a judgement about anyone's mental health.
- **Negation is simple.** It only looks a few words back. "Not only happy but relieved" is misread.
- **"Today" follows the server's clock.** Days for streaks and stats use the timezone of the machine running CalmConnect (set `TZ` in Docker). That's fine for a personal install, but it isn't built for a shared server with people in different timezones.
- **Entries aren't encrypted on disk**, there's no rate limiting on login, and Flask's built-in server isn't meant for the public internet. CalmConnect is meant to run on your own machine.

## Upgrading from the first version

The first version saved entries under a plain name, with no accounts. When the new version opens an old database, it moves those rows to a `legacy_entries` table instead of deleting them. Create an account, then run:

```bash
calmconnect import-legacy <the name you used before>
```

Entries are copied with their original text and date and re-analysed with the current rules. The old version didn't record times, so imported entries show midnight UTC.
