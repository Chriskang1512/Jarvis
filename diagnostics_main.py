from jarvis.chat import ProviderFactory
from jarvis.config import ConfigurationLoader
from jarvis.diagnostics import DiagnosticsCollector, DiagnosticsConsole


def main():
    """Render one Jarvis diagnostics snapshot."""
    config = ConfigurationLoader().load()
    collector = DiagnosticsCollector()
    provider = ProviderFactory().create(config)

    collector.log_event("Diagnostics started")
    collector.publish_provider(
        provider_name=getattr(provider.last_metadata, "provider_name", config.provider),
        model=getattr(provider.last_metadata, "model", config.model),
        finish_reason=getattr(provider.last_metadata, "finish_reason", ""),
        usage=getattr(provider.last_metadata, "usage", None),
        created_at=getattr(provider.last_metadata, "created_at", ""),
    )
    collector.publish_pipeline(
        wake="ready",
        stt="ready",
        llm="ready",
        tts="ready",
        current_stage="idle",
    )
    collector.publish_health(
        provider=check_provider_health(config.provider),
        voice="ready",
        pipeline="ready",
        overall="online",
    )
    collector.publish_performance(
        llm_latency=0.0,
        stt_latency=0.0,
        tts_latency=0.0,
        total_latency=0.0,
    )
    collector.increment_request_count()
    collector.log_event("Diagnostics snapshot rendered")

    console = DiagnosticsConsole()
    print(console.render(collector.get_snapshot()))


def check_provider_health(provider_name):
    """Return a simple provider health status."""
    if provider_name in ["mock", "openai", "claude"]:
        return "ready"

    return "unknown"


if __name__ == "__main__":
    main()
