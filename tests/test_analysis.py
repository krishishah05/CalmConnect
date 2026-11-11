import unittest

from app.analysis import analyze_text, classify_polarity, detect_emotions


class TestSentimentAnalysis(unittest.TestCase):
    def test_positive(self):
        result = analyze_text("I love sunny days and feel amazing")
        self.assertEqual(result["sentiment"], "positive")
        self.assertGreater(result["polarity"], 0.1)

    def test_negative(self):
        result = analyze_text("I hate everything, this is terrible")
        self.assertEqual(result["sentiment"], "negative")
        self.assertLess(result["polarity"], -0.1)

    def test_neutral(self):
        result = analyze_text("The sky is blue today")
        self.assertEqual(result["sentiment"], "neutral")

    def test_negated_positive_word_is_not_positive(self):
        result = analyze_text("I am not happy")
        self.assertNotEqual(result["sentiment"], "positive")
        self.assertNotIn("happy", result["emotions"])

    def test_empty_and_unusual_input(self):
        for text in ["", "   ", "!!!", "😀😀", None, "\n\n\t"]:
            with self.subTest(text=text):
                result = analyze_text(text)
                self.assertEqual(result["sentiment"], "neutral")
                self.assertEqual(result["polarity"], 0.0)
                self.assertEqual(result["emotions"], [])

    def test_classify_polarity_threshold(self):
        self.assertEqual(classify_polarity(0.1), "neutral")
        self.assertEqual(classify_polarity(0.11), "positive")
        self.assertEqual(classify_polarity(-0.1), "neutral")
        self.assertEqual(classify_polarity(-0.11), "negative")

    def test_sentiment_and_emotions_are_independent(self):
        # Tired is a negative-sounding word, but the entry as a whole is upbeat.
        result = analyze_text("Exhausted but so proud of what I finished today, it was wonderful")
        self.assertEqual(result["sentiment"], "positive")
        self.assertIn("tired", result["emotions"])
        self.assertIn("happy", result["emotions"])


class TestEmotionDetection(unittest.TestCase):
    def test_detects_anxious(self):
        self.assertIn("anxious", detect_emotions("I feel so anxious and stressed about tomorrow"))

    def test_detects_happy(self):
        self.assertIn("happy", detect_emotions("I am so happy today"))

    def test_detects_tired(self):
        self.assertIn("tired", detect_emotions("I am completely exhausted after work"))

    def test_detects_multiple(self):
        emotions = detect_emotions("I feel happy but also tired after the long day")
        self.assertEqual(emotions, ["happy", "tired"])

    def test_no_keywords(self):
        self.assertEqual(detect_emotions("I went to the store to buy groceries"), [])

    def test_case_insensitive(self):
        self.assertIn("anxious", detect_emotions("Feeling ANXIOUS about everything"))

    def test_whole_words_only(self):
        self.assertEqual(detect_emotions("We read about Madagascar downtown"), [])
        self.assertEqual(detect_emotions("I feel unhappy"), ["sad"])

    def test_simple_negation(self):
        self.assertEqual(detect_emotions("I am not happy"), [])
        self.assertEqual(detect_emotions("I'm not tired at all"), [])
        self.assertEqual(detect_emotions("I don't feel anxious anymore"), [])
        self.assertEqual(detect_emotions("I never felt lonely there"), [])

    def test_curly_apostrophe_negation(self):
        # Phones often type ’ instead of '.
        self.assertEqual(detect_emotions("I don’t feel anxious"), [])

    def test_negation_does_not_cross_clauses(self):
        self.assertEqual(detect_emotions("I wasn't sad, just tired"), ["tired"])
        self.assertEqual(detect_emotions("Not a great start, but happy now"), ["happy"])

    def test_negation_window_is_limited(self):
        # "not" is too far before "happy" to apply to it.
        self.assertEqual(
            detect_emotions("I did not expect the old town square to make me this happy"),
            ["happy"],
        )

    def test_negated_and_plain_mentions(self):
        self.assertEqual(detect_emotions("Not anxious this morning. Anxious again tonight."), ["anxious"])

    def test_multi_word_phrases(self):
        self.assertEqual(detect_emotions("Totally burnt out"), ["tired"])
        self.assertEqual(detect_emotions("I've been feeling down lately"), ["sad"])
        self.assertEqual(detect_emotions("I sat down by the canal"), [])

    def test_each_emotion_reported_once(self):
        self.assertEqual(detect_emotions("tired tired exhausted drained"), ["tired"])


if __name__ == "__main__":
    unittest.main()
