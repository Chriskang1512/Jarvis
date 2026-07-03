import logging
from time import perf_counter


class VoicePipeline:
    """Run the wake word, STT, LLM, and TTS pipeline."""

    def __init__(
        self,
        wake_listener,
        stt_provider,
        chat_service,
        tts_provider,
        logger=None,
        diagnostics_collector=None,
    ):
        """Create a voice pipeline with replaceable modules."""
        self.wake_listener = wake_listener
        self.stt_provider = stt_provider
        self.chat_service = chat_service
        self.tts_provider = tts_provider
        self.logger = logger or logging.getLogger("jarvis.voice")
        self.diagnostics_collector = diagnostics_collector

    def run_once(self):
        """Run one complete voice conversation turn."""
        total_start = perf_counter()
        stt_latency = 0.0
        llm_latency = 0.0
        tts_latency = 0.0

        self.logger.info("wake_word.waiting")
        self.publish_pipeline(wake="waiting", current_stage="wake")
        self.log_event("Wake waiting")
        self.wake_listener.wait_for_wake_word()
        self.logger.info("wake_word.detected")
        self.publish_pipeline(wake="detected", current_stage="stt")
        self.log_event("Wake detected")

        self.logger.info("stt.started")
        stt_start = perf_counter()
        self.publish_pipeline(stt="started", current_stage="stt")
        self.log_event("STT started")
        user_message = self.stt_provider.listen()
        stt_latency = perf_counter() - stt_start
        self.logger.info("stt.finished")
        self.publish_pipeline(stt="finished", current_stage="llm")
        self.log_event("STT finished")

        if user_message == "":
            self.logger.info("stt.empty")
            self.publish_pipeline(stt="empty", current_stage="idle")
            self.publish_performance(llm_latency, perf_counter() - total_start, stt_latency, tts_latency)
            self.log_event("STT returned empty input")
            return ""

        self.logger.info("llm.started")
        llm_start = perf_counter()
        self.publish_pipeline(llm="started", current_stage="llm")
        self.log_event("LLM started")
        reply = self.chat_service.generate_reply(user_message)
        llm_latency = perf_counter() - llm_start
        self.logger.info("llm.finished")
        self.publish_pipeline(llm="finished", current_stage="tts")
        self.publish_provider_metadata()
        self.log_event("LLM finished")

        self.logger.info("tts.started")
        tts_start = perf_counter()
        self.publish_pipeline(tts="started", current_stage="tts")
        self.log_event("TTS started")
        self.tts_provider.speak(reply)
        tts_latency = perf_counter() - tts_start
        self.logger.info("tts.finished")
        self.publish_pipeline(tts="finished", current_stage="idle")
        self.publish_performance(llm_latency, perf_counter() - total_start, stt_latency, tts_latency)
        self.log_event("TTS finished")

        return reply

    def publish_pipeline(self, wake=None, stt=None, llm=None, tts=None, current_stage=None):
        """Publish voice pipeline status when diagnostics is available."""
        if self.diagnostics_collector is None:
            return

        current_pipeline = self.diagnostics_collector.get_snapshot().pipeline
        self.diagnostics_collector.publish_pipeline(
            wake=choose_status(wake, current_pipeline.wake),
            stt=choose_status(stt, current_pipeline.stt),
            llm=choose_status(llm, current_pipeline.llm),
            tts=choose_status(tts, current_pipeline.tts),
            current_stage=choose_status(current_stage, current_pipeline.current_stage),
        )

    def publish_performance(self, llm_latency, total_latency, stt_latency, tts_latency):
        """Publish voice pipeline timing when diagnostics is available."""
        if self.diagnostics_collector is None:
            return

        self.diagnostics_collector.publish_performance(
            llm_latency=llm_latency,
            total_latency=total_latency,
            stt_latency=stt_latency,
            tts_latency=tts_latency,
        )

    def publish_provider_metadata(self):
        """Publish ChatProvider metadata when diagnostics is available."""
        if self.diagnostics_collector is None:
            return

        provider = self.chat_service.provider
        metadata = getattr(provider, "last_metadata", None)

        if metadata is None:
            return

        self.diagnostics_collector.publish_provider(
            provider_name=getattr(metadata, "provider_name", ""),
            model=getattr(metadata, "model", ""),
            finish_reason=getattr(metadata, "finish_reason", ""),
            usage=getattr(metadata, "usage", None),
            created_at=getattr(metadata, "created_at", ""),
        )

    def log_event(self, message):
        """Publish a diagnostics event when diagnostics is available."""
        if self.diagnostics_collector is None:
            return

        self.diagnostics_collector.log_event(message)


def choose_status(new_status, current_status):
    """Return the new status when provided, otherwise keep the current status."""
    if new_status is None:
        return current_status

    return new_status
