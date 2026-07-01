import unittest

from jarvis.brain.controller import find_agent_name


class TestBrainRouting(unittest.TestCase):
    """Test that Brain sends commands to the expected agent."""

    def test_memory_has_highest_priority(self):
        """Check that memory commands beat investment keywords."""
        self.assertEqual(find_agent_name("기억해 VOO 투자"), "memory")

    def test_invest_keywords(self):
        """Check that stock and ETF keywords go to Invest."""
        self.assertEqual(find_agent_name("주식 분석"), "invest")
        self.assertEqual(find_agent_name("SCHD 배당"), "invest")
        self.assertEqual(find_agent_name("QQQ 분석"), "invest")

    def test_japanese_keywords(self):
        """Check that Japanese and shorts keywords go to Japanese Shorts."""
        self.assertEqual(find_agent_name("일본어 번역"), "japanese")
        self.assertEqual(find_agent_name("니혼고 쇼츠"), "japanese")

    def test_music_keywords(self):
        """Check that music keywords go to Music YouTube."""
        self.assertEqual(find_agent_name("음악 유튜브"), "music")
        self.assertEqual(find_agent_name("노래 만들어줘"), "music")

    def test_scheduler_keywords(self):
        """Check that schedule keywords go to Scheduler."""
        self.assertEqual(find_agent_name("일정 예약"), "scheduler")

    def test_default_brain(self):
        """Check that unknown commands stay with Brain."""
        self.assertEqual(find_agent_name("오늘 기분 어때"), "brain")


if __name__ == "__main__":
    unittest.main()
