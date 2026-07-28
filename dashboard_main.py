"""Run Jarvis Dashboard as a local observability process."""

from jarvis.config import ConfigurationLoader
from jarvis.dashboard import DashboardBackend, ObservabilityHub
from jarvis.diagnostics import DiagnosticsCollector
from jarvis.memory_store import JsonMemoryStore, MemoryManager


def main():
    config = ConfigurationLoader().load()
    diagnostics = DiagnosticsCollector()
    memory = MemoryManager(
        store=JsonMemoryStore(config.memory_store.path),
        diagnostics_collector=diagnostics,
    )
    memory.load()
    hub = ObservabilityHub()
    hub.runtime.update(
        {
            "current_session": diagnostics.get_snapshot().session.session_id,
            "current_provider": config.provider,
        }
    )
    backend = DashboardBackend(hub, memory, diagnostics).start(background=False)
    return backend


if __name__ == "__main__":
    print("Jarvis Dashboard: http://127.0.0.1:8765")
    main()
