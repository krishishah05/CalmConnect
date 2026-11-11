# CalmConnect

CalmConnect started as a small journaling project built around a simple idea: sometimes, after a long day, you just need somewhere to put your thoughts. I've continued developing it over time, and journaling during my semester abroad has made me appreciate it even more. Being able to revisit what I was thinking and feeling during different trips is something I know I'll love looking back on.

It's a private journal you can use from the terminal or the browser. You can tag entries by trip or city, search for a place later, and read everything from one trip back in order. It does some light analysis of the words you write, but it isn't a therapist or a chatbot, and it doesn't pretend to know how you feel.

![The Travel collection, with entries in the order they were written](docs/screenshots/trip.png)
<sub>A collection in the browser, using the sample entries from the demo journal.</sub>

## What it does

- Write, edit and delete entries. Each one can have a title, a place and tags, and you can backdate an entry if you missed a day.
- If you don't know where to start, it can give you a prompt.
- Every tag becomes a collection. Tag entries `italy` or `dublin` and you can read that trip from start to finish, with a small timeline and summary of how the tone of your writing changed along the way.
- Search text, titles and places (so searching a city finds entries from there), and filter by tag or date range. Filters combine, so you can search within one trip.
- A weekly reflection shows which days you wrote, the mix of tones, the feelings that came up most and your streaks, summed up in a few plain sentences.
- "Looking back" brings up an older entry, preferring one from this day in an earlier year.

## How the analysis works

I wanted something small enough that I could explain every part of it, so there's no machine learning model here.

Each entry gets two separate readings. The tone (positive, neutral or negative) comes from [TextBlob](https://textblob.readthedocs.io/)'s polarity score, which goes from -1 to 1. Anything between -0.1 and 0.1 counts as neutral.

Feelings (happy, calm, grateful, sad, anxious, angry, tired) come from a short word list in [`app/analysis.py`](app/analysis.py). It matches whole words, so "unhappy" isn't happy and "downtown" isn't "down". It also skips a feeling if "not", "never", "don't" or something similar shows up a few words before it in the same clause, so in "I wasn't sad, just tired", only tired counts.

The two readings can disagree, and that's fine. "Exhausted but proud of today" is positive in tone and still tired.

For the weekly numbers, each day's tone is the average of that day's entries, and every day counts the same. Otherwise one rough day with five entries would outweigh the rest of the week.

## Getting started

You'll need Python 3.10 or newer.

```bash
git clone https://github.com/krishishah05/CalmConnect
cd CalmConnect
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

That installs Flask, TextBlob and Rich and gives you a `calmconnect` command. Everything is saved in `./data` (your journal, a generated secret key and your CLI login), and git ignores that folder. [`.env.example`](.env.example) lists the optional settings.

## Trying it with sample entries

If you want to look around before writing anything, `demo.py` creates a separate demo journal in `demo-data/` with seven short sample entries from a semester abroad: Iceland, Prague, Barcelona, Rome, the Amalfi Coast, Dublin and Morocco.

```bash
python demo.py            # prints a generated password for the "demo" account
CALMCONNECT_DATA_DIR=demo-data flask --app api.main run
CALMCONNECT_DATA_DIR=demo-data calmconnect login demo

python demo.py --reset    # delete the demo journal and start over
```

These are illustrative sample reflections, not diary entries from those exact days. Only the month or date range of each trip is known, so each entry sits on the first day of its period (the October trips all show October 1). The demo never opens your real journal in `data/`, and it won't overwrite an existing demo unless you pass `--reset`. The weekly reflection only covers the last seven days, so after a while the demo week will be empty, but collections, search and "Looking back" still work.

## From the terminal

```bash
calmconnect register
calmconnect journal                              # type freely, finish with Ctrl-D
calmconnect journal --prompt
calmconnect journal "Your entry here" --place "Prague, Czech Republic" --tags prague,study-abroad
calmconnect journal "Writing about a day I missed" --date 2026-11-07

calmconnect history --tag italy --oldest         # read a trip in order
calmconnect history -s dublin                    # search text, titles and places
calmconnect history --tag travel -s halloween    # search within a trip
calmconnect history --from 2026-10-01 --to 2026-10-31
calmconnect show 12
calmconnect edit 12                              # opens $EDITOR
calmconnect edit 12 --tags travel,ireland
calmconnect delete 12

calmconnect reflect                              # your week, plus an older entry
calmconnect stats
calmconnect tags                                 # every tag, with dates
calmconnect tags travel                          # one collection, in order
```

Here's the start of `calmconnect tags travel` in the demo journal:

```
#travel  6 entries, 2026-08-01 to 2026-11-06

 Aug 1    Oct 1     Oct 30    Nov 6
neutral  positive  positive  positive
The tone of your writing stayed fairly steady throughout.
Feelings named most: happy (2)
```

Every command has `--help`. If you don't want to install it, `python -m cli.main` works the same way from the project folder.

## In the browser

```bash
flask --app api.main run
```

Then open http://127.0.0.1:5000 and make an account. There are four pages: Write, Journal, Collections and Reflect. It's plain HTML and CSS with no JavaScript, works on a phone, and follows your system's dark mode.

<p>
  <img src="docs/screenshots/search.png" width="49%" alt="Searching the journal for Italy">
  <img src="docs/screenshots/reflect.png" width="49%" alt="The weekly reflection page">
</p>

There's also a Dockerfile and `docker-compose.yml` if you'd rather run it in a container (`docker compose up --build`). I mostly run CalmConnect directly on my laptop, so the Docker setup is less tested.

## The API

The same Flask app has a JSON API under `/api`. Log in once to get a token, then send it as `Authorization: Bearer <token>`.

```bash
curl -X POST localhost:5000/api/tokens -H "Content-Type: application/json" \
     -d '{"username": "krishi", "password": "a long password"}'
```

| Route | What it does |
| --- | --- |
| `POST /api/register` | Create an account (`username`, `password`) |
| `POST /api/tokens` | Log in and get a token, valid for 30 days |
| `DELETE /api/tokens/current` | Log out by revoking the token |
| `GET /api/entries` | List entries. Optional: `q`, `tag`, `from`, `to`, `order=newest\|oldest`, `limit` (1 to 100), `offset` |
| `POST /api/entries` | Create an entry: `text`, plus optional `title`, `place`, `tags`, `date`, `prompt` |
| `GET`, `PATCH`, `DELETE /api/entries/<id>` | Read, change (any of `text`, `title`, `place`, `tags`, `date`) or delete one entry |
| `GET /api/tags` | Your tags, with entry counts and date ranges |
| `GET /api/tags/<tag>` | One collection: its entries in order, a timeline and a tone summary |
| `GET /api/stats` | The weekly summary and streaks |
| `GET /api/revisit` | An older entry to look back on |

Errors come back as `{"error": "..."}`. If you ask for someone else's entry, you get the same 404 as for one that doesn't exist.

## Privacy

Journal entries are personal, so I tried to be careful here:

- Passwords are hashed with scrypt (through Werkzeug), and there are no built-in accounts or default passwords.
- The browser, CLI and API all log in with the same kind of token. Only a SHA-256 hash of each token is stored, tokens expire after 30 days, and logging out deletes them.
- Tokens never go in URLs. The browser keeps its token in a signed HttpOnly cookie, and every form has a CSRF token.
- Every database query that touches entries is limited to the logged-in user.
- The `data` folder is created so only your OS user can read it, and the CLI can't act as another person without their password.
- The server runs without debug mode and only listens on 127.0.0.1 unless you change it.

## Tests

```bash
python -m unittest discover tests
```

They cover the analysis edge cases, entry validation, search and filters, streaks and weekly stats around date boundaries, trip collections after edits and deletes, migrating an old database, logins, keeping users' journals separate, and the API, web pages and CLI end to end.

## How the code is laid out

```
app/analysis.py   tone and feelings for a piece of text
app/auth.py       accounts, password hashing and login tokens
app/journal.py    validation and journal operations used by every interface
app/stats.py      streaks, weekly summaries and collection summaries
app/storage.py    SQLite schema and queries
api/main.py       Flask app setup and the JSON API
api/web.py        browser pages (templates/ and static/ sit next to it)
cli/main.py       the calmconnect command
demo.py           creates the optional demo journal
tests/            one test file per area
docs/screenshots  the images in this README
```

## Limitations

- The analysis only looks at words. It misses sarcasm, slang, emoji and most non-English writing, and any feeling that isn't in the word list. TextBlob also gets some sentences wrong: "I don't feel anxious anymore" comes out slightly negative. Treat it as a rough summary of what you wrote, not a judgement about anyone's mental health.
- Negation is simple. It only looks a few words back, so "Not only happy but relieved" gets misread.
- "Today" follows the clock of the computer running CalmConnect. That's fine for a personal setup, but it isn't built for a shared server with people in different timezones.
- Entries aren't encrypted on disk, there's no rate limiting on login, and Flask's built-in server isn't meant for the public internet. It's meant to run on your own machine.

## Upgrading from the first version

The first version saved entries under a plain name with no accounts. When the new version opens an old database, it moves those rows to a `legacy_entries` table instead of deleting them. Make an account, then run:

```bash
calmconnect import-legacy <the name you used before>
```

Entries come across with their original text and date and get re-analysed with the current rules. The old version didn't save times, so imported entries show midnight UTC.
