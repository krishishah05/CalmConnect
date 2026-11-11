# CalmConnect

CalmConnect started as a small personal project because I wanted somewhere to write down my thoughts at the end of the day. Over time it grew into a way to keep track of little moments, notice how I was feeling, and come back to experiences I didn't want to forget.

While studying abroad, I've especially enjoyed journaling about the places I've visited and the things I've experienced. When I look back on this semester, I want to remember more than photos and itineraries. I want to remember what those days actually felt like.

So that's what CalmConnect is: a private journal you can use from the terminal or a browser. You write, it keeps your entries safe and searchable, and it gives you a gentle look back at your week or at a whole trip. It is not a therapist or a chatbot, and it doesn't try to tell you how you feel.

## Features

- **Write, edit and delete entries.** Each entry can have an optional title, place and tags, and you can backdate one if you missed a day.
- **Reflection prompts** for when you sit down and don't know where to start.
- **Collections.** Tags like `morocco` or `copenhagen` group entries together, so you can read a whole trip from start to finish and see how the tone of your writing changed along the way.
- **Search and filters.** Search text, titles and places, and filter by tag or date range, oldest or newest first.
- **Weekly reflection.** Writing tone per day, overall mix of tones, feelings that came up most, how many days you wrote, and current and longest streaks, summed up in a few plain sentences.
- **Looking back.** Shows an older entry, preferring one written on this day in an earlier year.
- **Accounts.** Each person's journal is private to them in the CLI, web pages and API.

## How the analysis works

Each entry gets two separate readings:

- **Tone** (positive, neutral or negative) comes from [TextBlob](https://textblob.readthedocs.io/)'s polarity score, which runs from -1 to 1. Anything between -0.1 and 0.1 counts as neutral.
- **Feelings** (happy, calm, grateful, sad, anxious, angry, tired) come from a small word list in [`app/analysis.py`](app/analysis.py). Matching is on whole words and short phrases, so "unhappy" doesn't count as happy and "downtown" isn't "down". A feeling is skipped if a negation ("not", "never", "don't" and so on) appears up to three words before it in the same clause, so "I'm not tired" doesn't count as tired. Negation stops at punctuation and words like "but", so in "I wasn't sad, just tired" only *tired* counts.

The two can disagree, and that's on purpose. "Exhausted but proud of today" reads as positive in tone while still naming *tired*.

In the weekly view, each day's tone is the average of that day's entries, and the week's average weights every day equally, so one day with five entries doesn't outweigh the rest.

## Getting started

You'll need Python 3.10 or newer.

```bash
git clone https://github.com/krishishah05/CalmConnect
cd CalmConnect
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

This installs Flask, TextBlob and Rich, and adds a `calmconnect` command. Everything is stored in `./data` (the database, a generated secret key and your CLI login). That folder is ignored by git. Set `CALMCONNECT_DATA_DIR` to keep it somewhere else; see [`.env.example`](.env.example) for the other settings.

## Using the CLI

```bash
calmconnect register                     # create an account; you stay logged in
calmconnect journal                      # type freely, finish with Ctrl-D
calmconnect journal --prompt             # start with a question
calmconnect journal "Long day, but the walk home helped." --tags school

calmconnect journal --title "Nyhavn" --place Copenhagen --tags travel,copenhagen
calmconnect journal "Finally wrote about Saturday." --date 2026-11-07
```

Finding things again:

```bash
calmconnect history                      # recent entries
calmconnect history --tag copenhagen --oldest
calmconnect history -s "bakery"          # searches text, titles and places
calmconnect history --on 2026-10-02      # one specific day
calmconnect show 12
```

Making changes:

```bash
calmconnect edit 12                      # opens $EDITOR, or asks for new text
calmconnect edit 12 --title "Lost in the medina" --tags travel,morocco
calmconnect delete 12                    # asks before deleting
```

Looking back:

```bash
calmconnect reflect                      # your week in a few sentences, plus an older entry
calmconnect stats                        # the numbers behind it
calmconnect tags                         # every tag, with dates
calmconnect tags morocco                 # one trip, in order, and how it felt along the way
```

Here's what `tags` looks like after a trip:

```
#morocco  4 entries, 2026-10-01 to 2026-10-06

 Oct 1     Oct 2     Oct 4     Oct 6
positive  positive  positive  negative
Your writing sounded more negative toward the end than at the start.
Feelings named most: grateful (2), anxious (1), calm (1)
```

`calmconnect --help` and `calmconnect <command> --help` list every option. If you'd rather not install the package, `python -m cli.main` works the same way from the project folder.

## Using the web app

```bash
flask --app api.main run
```

Then open http://127.0.0.1:5000 and create an account. The pages are plain HTML and CSS, with no JavaScript: **Write**, **Journal** (search and filters), **Collections** (one page per tag) and **Reflect** (your week). It follows your system's light or dark mode.

You can also run it with Docker, which keeps your data in `./data` and only listens on localhost:

```bash
docker compose up --build
```

## The JSON API

The same Flask app serves a JSON API under `/api`. Log in once to get a token, then send it in the `Authorization` header:

```bash
curl -X POST localhost:5000/api/register -H "Content-Type: application/json" \
     -d '{"username": "krishi", "password": "a long password"}'

curl -X POST localhost:5000/api/tokens -H "Content-Type: application/json" \
     -d '{"username": "krishi", "password": "a long password"}'
# {"token": "...", "expires_in_days": 30}

curl -X POST localhost:5000/api/entries -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"text": "Rainy day by the canal.", "place": "Copenhagen", "tags": ["copenhagen"]}'
```

| Method and path | What it does |
| --- | --- |
| `POST /api/register` | Create an account |
| `POST /api/tokens` | Log in and get a token |
| `DELETE /api/tokens/current` | Log out (revokes the token) |
| `GET /api/entries` | List entries. Query options: `q`, `tag`, `from`, `to`, `order=newest\|oldest`, `limit` (1 to 100), `offset` |
| `POST /api/entries` | Create an entry: `text`, plus optional `title`, `place`, `tags`, `date`, `prompt` |
| `GET /api/entries/<id>` | Read one entry |
| `PATCH /api/entries/<id>` | Change any of `text`, `title`, `place`, `tags`, `date` |
| `DELETE /api/entries/<id>` | Delete an entry |
| `GET /api/stats` | Weekly summary and streaks |
| `GET /api/tags` | Tags with entry counts and date ranges |
| `GET /api/tags/<tag>` | One collection: entries in order, timeline and tone summary |
| `GET /api/prompt` | A random reflection prompt |
| `GET /api/revisit` | An older entry to look back on |

Errors come back as `{"error": "..."}` with a matching status code. An entry that belongs to someone else returns the same 404 as one that doesn't exist.

## Privacy and security

- Passwords are hashed with Werkzeug's scrypt.
- The web app, CLI and API all log in with a random token. The database stores only a SHA-256 hash of each token, so a copy of the database can't be used to log in. Tokens expire, and logging out deletes them.
- Tokens never go in URLs. The API reads them from the `Authorization` header. The web app keeps one in a signed, HttpOnly, SameSite cookie, and every form has a CSRF token.
- Every query that touches entries includes the owner's user id, so one account can't read, edit or delete another's entries.
- The CLI keeps its login in `data/cli_session`, readable only by your OS user. It no longer takes a username argument, so it can't be used to read someone else's journal.
- There are no built-in accounts or default passwords. The session secret comes from `CALMCONNECT_SECRET_KEY` or is generated on first run.
- The server runs without Flask's debug mode and listens on 127.0.0.1 by default.

## Running the tests

```bash
python -m unittest discover tests
```

The tests cover sentiment and emotion edge cases, entry validation, editing and deleting, search and filters, streaks and weekly stats around date boundaries, trip collections, authentication, user isolation, and the API, web pages and CLI end to end. Each test uses its own temporary data folder.

## Project structure

```
app/
  analysis.py   tone and feelings for a piece of text
  auth.py       accounts, password hashing and login tokens
  journal.py    validation and journal operations shared by every interface
  stats.py      streaks, the weekly summary and collection summaries
  storage.py    SQLite schema and queries
api/
  main.py       Flask app setup and the JSON API
  web.py        browser pages
  templates/    Jinja templates
  static/       one stylesheet
cli/
  main.py       the calmconnect command
tests/          unittest suites for each part
```

`journal.py` is the layer the CLI, API and web pages all go through, so validation and analysis happen the same way no matter where an entry comes from.

## Known limitations

- **The analysis only sees words.** It misses sarcasm, mixed feelings inside one sentence, slang, emoji and most non-English writing. TextBlob sometimes scores sentences oddly ("I don't feel anxious anymore" comes out slightly negative), and a feeling that isn't in the word list isn't detected at all. Treat the tone and feelings as a rough summary, never as a judgement about your mental health.
- **Negation is simple.** It looks a few words back within a clause. "Not only happy but relieved" won't be read correctly.
- **"Today" means the server's timezone.** Days for streaks and stats come from the clock of the machine running CalmConnect (set `TZ` in Docker). That's fine for a personal install, but people in other timezones sharing one server would see days split at the wrong time.
- **Entries aren't encrypted on disk.** Anyone with access to your OS account or the database file can read them.
- **No rate limiting** on login, and Flask's built-in server isn't meant for the public internet. CalmConnect is designed to run on your own machine.
- **Editing in the CLI** without `$EDITOR` set means retyping the whole entry.

## Upgrading from the first version

The original version stored entries under a free-text name with no accounts. On first run, those rows are moved to a `legacy_entries` table rather than deleted. Create an account, then bring them in with:

```bash
calmconnect import-legacy <old-name>
```

They're re-analysed with the current rules. The old version only stored dates, so imported entries show a time of midnight UTC.
