"""Lightweight sentiment and emotion analysis for journal entries.

Two separate signals are produced:

* sentiment - the overall tone of the writing (positive / neutral / negative),
  taken from TextBlob's polarity score in the range -1.0 to 1.0.
* emotions - specific feelings that are named in the text, found by matching
  whole words and short phrases against a small hand-written lexicon.

They can disagree, and that's fine: "I'm exhausted but proud of today" is
tired *and* positive. Neither signal knows how the writer actually feels; they
only describe the words on the page.
"""

import re

from textblob import TextBlob

# Polarity has to clear this margin before we call the tone positive/negative.
# TextBlob gives small non-zero scores to fairly flat sentences.
SENTIMENT_THRESHOLD = 0.1

# Keys are the emotion labels we report. Entries can be single words or short
# phrases; matching is on whole words, so "happy" never matches "unhappy".
EMOTION_LEXICON = {
    "happy": [
        "happy", "glad", "joy", "joyful", "excited", "thrilled", "delighted",
        "cheerful", "proud", "amazing", "wonderful", "fun",
    ],
    "calm": [
        "calm", "calmer", "relaxed", "peaceful", "rested", "at peace",
        "at ease",
    ],
    "grateful": ["grateful", "thankful", "appreciative", "blessed"],
    "sad": [
        "sad", "unhappy", "depressed", "lonely", "hopeless", "grief",
        "grieving", "crying", "cried", "miserable", "heartbroken", "upset",
        "feel down", "feeling down", "felt down",
    ],
    "anxious": [
        "anxious", "anxiety", "worried", "worry", "nervous", "stressed",
        "stress", "overwhelmed", "panic", "panicking", "scared", "afraid",
        "fearful", "on edge",
    ],
    "angry": [
        "angry", "furious", "annoyed", "frustrated", "frustrating", "rage",
        "mad", "irritated", "resentful", "fed up",
    ],
    "tired": [
        "tired", "exhausted", "exhausting", "drained", "burnt out",
        "burned out", "burnout", "fatigued", "sleepy", "worn out",
    ],
}

# Words that flip the meaning of an emotion word shortly after them.
NEGATIONS = {
    "not", "no", "never", "without", "hardly", "barely", "nor", "neither",
    "cannot",
}
# How many words back from an emotion word we look for a negation.
NEGATION_WINDOW = 3

# Negation doesn't carry across these, e.g. "not great, but happy".
_CLAUSE_SPLIT = re.compile(r"[.,;:!?\n]+|\bbut\b|\bthough\b|\balthough\b")
_WORD = re.compile(r"[a-z]+(?:'[a-z]+)?")

# First word -> [(phrase as a tuple of words, emotion)], so each word in an
# entry only gets compared against phrases that could start with it.
_PHRASES_BY_FIRST_WORD: dict[str, list[tuple[tuple[str, ...], str]]] = {}
for _emotion, _phrases in EMOTION_LEXICON.items():
    for _phrase in _phrases:
        _words = tuple(_phrase.split())
        _PHRASES_BY_FIRST_WORD.setdefault(_words[0], []).append((_words, _emotion))


def _is_negation(word: str) -> bool:
    return word in NEGATIONS or word.endswith("n't")


def _clauses(text: str) -> list[list[str]]:
    """Lowercase the text and split it into clauses of words."""
    text = text.lower().replace("’", "'")  # curly apostrophes from phones
    return [_WORD.findall(part) for part in _CLAUSE_SPLIT.split(text)]


def detect_emotions(text: str) -> list[str]:
    """Return emotion labels named in the text, in order of first appearance.

    A match is ignored when a negation appears up to NEGATION_WINDOW words
    earlier in the same clause, so "not happy" and "I don't feel anxious"
    don't count. A negated emotion is *not* turned into its opposite;
    "not happy" tells us less than it seems to.
    """
    found: list[str] = []
    for words in _clauses(text):
        for i, word in enumerate(words):
            for phrase, emotion in _PHRASES_BY_FIRST_WORD.get(word, []):
                if emotion in found or tuple(words[i:i + len(phrase)]) != phrase:
                    continue
                window = words[max(0, i - NEGATION_WINDOW):i]
                if not any(_is_negation(w) for w in window):
                    found.append(emotion)
    return found


def classify_polarity(polarity: float) -> str:
    if polarity > SENTIMENT_THRESHOLD:
        return "positive"
    if polarity < -SENTIMENT_THRESHOLD:
        return "negative"
    return "neutral"


def analyze_text(text: str) -> dict:
    """Return {"sentiment", "polarity", "emotions"} for a piece of text.

    Empty or whitespace-only text is treated as neutral with no emotions
    rather than raising, so callers can decide how to handle it.
    """
    text = (text or "").strip()
    polarity = TextBlob(text).sentiment.polarity if text else 0.0
    return {
        "sentiment": classify_polarity(polarity),
        "polarity": round(polarity, 4),
        "emotions": detect_emotions(text),
    }


def analyze_sentiment(text: str) -> dict:
    """Old name and result shape, kept until the callers move to analyze_text."""
    result = analyze_text(text)
    return {"mood": result["sentiment"], "polarity": result["polarity"],
            "emotions": result["emotions"]}
