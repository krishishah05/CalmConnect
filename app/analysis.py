from textblob import TextBlob

EMOTION_KEYWORDS = {
    "anxious": ["anxious", "anxiety", "worried", "nervous", "stressed", "overwhelmed", "panic", "scared", "fearful"],
    "sad": ["sad", "depressed", "lonely", "hopeless", "grief", "crying", "miserable", "heartbroken", "down"],
    "angry": ["angry", "furious", "annoyed", "frustrated", "rage", "hate", "mad", "irritated"],
    "happy": ["happy", "joy", "joyful", "excited", "grateful", "love", "wonderful", "great", "amazing", "thrilled"],
    "tired": ["tired", "exhausted", "drained", "burnt out", "burnout", "fatigued", "sleepy", "worn out"],
}


def detect_emotions(text):
    lower = text.lower()
    found = []
    for emotion, keywords in EMOTION_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            found.append(emotion)
    return found


def analyze_sentiment(text):
    blob = TextBlob(text)
    polarity = blob.sentiment.polarity

    if polarity > 0.1:
        mood = "positive"
    elif polarity < -0.1:
        mood = "negative"
    else:
        mood = "neutral"

    return {
        "mood": mood,
        "polarity": round(polarity, 4),
        "emotions": detect_emotions(text),
    }
