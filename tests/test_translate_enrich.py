import unittest

from proto.translate_enrich import extract_verbatim_tokens, reinject_verbatim_tokens, translate_enrich


class TestVerbatimTokenExtraction(unittest.TestCase):
    def test_version_number_is_protected(self):
        masked, mapping = extract_verbatim_tokens("Upgrade to version 3.11.2 now.")
        self.assertNotIn("3.11.2", masked)
        self.assertIn("3.11.2", mapping.values())

    def test_license_identifier_is_protected(self):
        masked, mapping = extract_verbatim_tokens("The project uses the MIT license.")
        self.assertNotIn("MIT", masked)

    def test_reinject_restores_original_text(self):
        original = "Python 3.12 uses the MIT license."
        masked, mapping = extract_verbatim_tokens(original)
        restored = reinject_verbatim_tokens(masked, mapping)
        self.assertEqual(restored, original)


class TestTranslateEnrich(unittest.TestCase):
    def test_identity_translate_fn_round_trips(self):
        original = "Python 3.12 uses the MIT license, released in October."
        result = translate_enrich(original, translate_fn=lambda text: text)
        self.assertEqual(result, original)

    def test_verbatim_tokens_survive_a_lossy_translate_fn(self):
        original = "Version 2.0.1 ships under Apache-2.0."

        def lossy_translate(text: str) -> str:
            # simulates a translation call that mangles connective tissue but
            # must leave the __TOKn__ placeholders untouched
            return text.replace("ships under", "est distribué sous")

        result = translate_enrich(original, translate_fn=lossy_translate)
        self.assertIn("2.0.1", result)
        self.assertIn("Apache-2.0", result)
        self.assertIn("est distribué sous", result)


if __name__ == "__main__":
    unittest.main()
