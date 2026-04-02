import unittest
from app.analysis import analyze_sentiment, detect_emotions


class TestSentimentAnalysis(unittest.TestCase):
    def test_positive(self):
        result = analyze_sentiment("I love sunny days and feel amazing")
        self.assertEqual(result["mood"], "positive")
        self.assertGreater(result["polarity"], 0.1)

    def test_negative(self):
        result = analyze_sentiment("I hate everything, this is terrible")
        self.assertEqual(result["mood"], "negative")
        self.assertLess(result["polarity"], -0.1)

    def test_neutral(self):
        result = analyze_sentiment("The sky is blue today")
        self.assertEqual(result["mood"], "neutral")

    def test_polarity_bounds(self):
        result = analyze_sentiment("okay I guess")
        self.assertGreaterEqual(result["polarity"], -1.0)
        self.assertLessEqual(result["polarity"], 1.0)

    def test_returns_required_keys(self):
        result = analyze_sentiment("feeling fine")
        self.assertIn("mood", result)
        self.assertIn("polarity", result)
        self.assertIn("emotions", result)

    def test_emotions_is_list(self):
        result = analyze_sentiment("I went for a walk")
        self.assertIsInstance(result["emotions"], list)


class TestEmotionDetection(unittest.TestCase):
    def test_detects_anxious(self):
        emotions = detect_emotions("I feel so anxious and stressed about tomorrow")
        self.assertIn("anxious", emotions)

    def test_detects_happy(self):
        emotions = detect_emotions("I am so happy and grateful today")
        self.assertIn("happy", emotions)

    def test_detects_tired(self):
        emotions = detect_emotions("I am completely exhausted after work")
        self.assertIn("tired", emotions)

    def test_detects_multiple(self):
        emotions = detect_emotions("I feel happy but also tired after the long day")
        self.assertIn("happy", emotions)
        self.assertIn("tired", emotions)

    def test_no_keywords(self):
        emotions = detect_emotions("I went to the store to buy groceries")
        self.assertEqual(emotions, [])

    def test_case_insensitive(self):
        emotions = detect_emotions("Feeling ANXIOUS about everything")
        self.assertIn("anxious", emotions)


if __name__ == "__main__":
    unittest.main()
