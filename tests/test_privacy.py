import unittest

from jarvis.privacy import contains_sensitive_text, redact_sensitive_text


class TestPrivacyHelpers(unittest.TestCase):
    def test_redacts_korean_mobile_numbers_for_logs(self):
        text = redact_sensitive_text("phone=010-5508-8235")

        self.assertIn("010-****-8235", text)
        self.assertNotIn("5508", text)

    def test_redacts_international_korean_mobile_numbers_for_logs(self):
        text = redact_sensitive_text("phone=+821055088235")

        self.assertIn("+82-****-8235", text)
        self.assertNotIn("5508", text)

    def test_redacts_email_addresses_for_logs(self):
        text = redact_sensitive_text("email=yui@example.com")

        self.assertIn("y***@example.com", text)
        self.assertNotIn("yui@example.com", text)

    def test_detects_sensitive_tts_text(self):
        self.assertTrue(contains_sensitive_text("phone=010-5508-8235"))
        self.assertTrue(contains_sensitive_text("email=aya@example.com"))
        self.assertFalse(contains_sensitive_text("contact_not_found"))

    def test_does_not_redact_iso_timestamps_as_phone_numbers(self):
        text = "2026-07-18T21:08:38"

        self.assertEqual(redact_sensitive_text(text), text)


if __name__ == "__main__":
    unittest.main()
