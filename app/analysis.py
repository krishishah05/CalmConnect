from textblob import TextBlob

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
        "polarity": polarity
    }
