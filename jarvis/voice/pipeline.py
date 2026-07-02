import logging


class VoicePipeline:
    """Run the wake word, STT, LLM, and TTS pipeline."""

    def __init__(self, wake_listener, stt_provider, chat_service, tts_provider, logger=None):
        """Create a voice pipeline with replaceable modules."""
        self.wake_listener = wake_listener
        self.stt_provider = stt_provider
        self.chat_service = chat_service
        self.tts_provider = tts_provider
        self.logger = logger or logging.getLogger("jarvis.voice")

    def run_once(self):
        """Run one complete voice conversation turn."""
        self.logger.info("wake_word.waiting")
        self.wake_listener.wait_for_wake_word()
        self.logger.info("wake_word.detected")

        self.logger.info("stt.started")
        user_message = self.stt_provider.listen()
        self.logger.info("stt.finished")

        if user_message == "":
            self.logger.info("stt.empty")
            return ""

        self.logger.info("llm.started")
        reply = self.chat_service.generate_reply(user_message)
        self.logger.info("llm.finished")

        self.logger.info("tts.started")
        self.tts_provider.speak(reply)
        self.logger.info("tts.finished")

        return reply
