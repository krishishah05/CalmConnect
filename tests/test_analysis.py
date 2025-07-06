import unittest
from app.analysis import analyze_sentiment

class TestAnalysis(unittest.TestCase):
    def test_positive(self):
        result = analyze_sentiment("I love sunny days")
        self.assertEqual(result["mood"], "positive")

    def test_negative(self):
        result = analyze_sentiment("I hate everything")
        self.assertEqual(result["mood"], "negative")

    def test_neutral(self):
        result = analyze_sentiment("The sky is blue")
        self.assertEqual(result["mood"], "neutral")

if __name__ == '__main__':
    unittest.main()
