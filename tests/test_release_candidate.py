import inspect
import unittest

from jarvis.agent_runtime import AgentRuntime, ExecutionKernel
from jarvis.agent_runtime import service as agent_runtime_service_module
from jarvis.execution import ExecutionGraphRunner
from jarvis.result_merge import DefaultResultMerger, ResultMerger
from jarvis.scheduler import InMemoryScheduler, Scheduler
from jarvis.scheduler import service as scheduler_service_module
from jarvis.voice import VoiceService
from jarvis.voice import service as voice_service_module


class TestReleaseCandidate(unittest.TestCase):
    """RC checks for v0.4.0 stable architecture contracts."""

    def test_stable_public_apis_are_exposed(self):
        """Check v0.4.0 stable public API surface."""
        self.assertTrue(hasattr(ExecutionGraphRunner, "run"))
        self.assertTrue(hasattr(ExecutionGraphRunner, "run_unified"))
        self.assertTrue(hasattr(ResultMerger, "merge"))
        self.assertTrue(hasattr(DefaultResultMerger, "merge"))
        self.assertTrue(hasattr(VoiceService, "speak"))

        for name in ["schedule", "get", "list", "cancel", "due_tasks", "trigger_due"]:
            self.assertTrue(hasattr(Scheduler, name))
            self.assertTrue(hasattr(InMemoryScheduler, name))

        for name in ["start", "stop", "tick"]:
            self.assertTrue(hasattr(AgentRuntime, name))

    def test_execution_kernel_protocol_is_run_unified_interface(self):
        """Check ExecutionKernel is the stable run_unified interface."""
        self.assertTrue(hasattr(ExecutionKernel, "run_unified"))
        self.assertIn("Stable execution interface", inspect.getdoc(ExecutionKernel))
        self.assertIn("UnifiedResult", inspect.getdoc(ExecutionKernel))

    def test_import_boundaries_remain_stable(self):
        """Check Voice, Scheduler, and AgentRuntime keep forbidden imports out."""
        boundary_sources = {
            "voice": inspect.getsource(voice_service_module),
            "scheduler": inspect.getsource(scheduler_service_module),
            "agent_runtime": inspect.getsource(agent_runtime_service_module),
        }
        forbidden = [
            "jarvis.planner",
            "jarvis.capabilities",
            "IntentPlanner",
            "Capability",
        ]

        for layer, source in boundary_sources.items():
            for value in forbidden:
                self.assertNotIn(value, source, f"{layer} imports forbidden layer {value}")

        self.assertNotIn("jarvis.execution", boundary_sources["voice"])
        self.assertNotIn("jarvis.voice", boundary_sources["scheduler"])
        self.assertNotIn("jarvis.voice", boundary_sources["agent_runtime"])


if __name__ == "__main__":
    unittest.main()
