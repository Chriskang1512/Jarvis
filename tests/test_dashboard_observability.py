import json
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from jarvis.dashboard import DashboardBackend, DashboardEventBridge, ObservabilityHub
from jarvis.dashboard.observability import _task_graph_metrics
from jarvis.events import JarvisEvent, JarvisEventType, JarvisState, JarvisStatus
from jarvis.memory_store import InMemoryStore, MemoryManager


class TestDashboardObservability(unittest.TestCase):
    def test_parallel_graph_metrics_separate_accumulated_and_critical_path_time(self):
        metrics = _task_graph_metrics(
            {
                "nodes": {
                    "search": {
                        "node_id": "search",
                        "duration_ms": 100,
                        "dependencies": [],
                    },
                    "calendar": {
                        "node_id": "calendar",
                        "duration_ms": 200,
                        "dependencies": [],
                    },
                    "summary": {
                        "node_id": "summary",
                        "duration_ms": 50,
                        "dependencies": ["search", "calendar"],
                    },
                },
                "replay_events": [
                    {"timestamp": "2026-07-28T11:00:00+09:00"},
                    {"timestamp": "2026-07-28T11:00:00.260000+09:00"},
                ],
            }
        )

        self.assertEqual(metrics["provider_ms"], 350.0)
        self.assertEqual(metrics["critical_path_ms"], 250.0)
        self.assertEqual(metrics["total_ms"], 260.0)
        self.assertEqual(metrics["parallel_efficiency"], 0.7143)
        self.assertEqual(metrics["provider_concurrency"], 1.3462)

    def setUp(self):
        self.config_path = Path(__file__).with_name(".dashboard-test-config.json")
        self.config_path.write_text(
            '{"provider":"mock","debug":false,"weather":{"provider":"openweather"},'
            '"tts":{"provider":"openai"},"stt":{"provider":"openai"}}',
            encoding="utf-8",
        )
        self.memory = MemoryManager(store=InMemoryStore())
        self.memory.remember("강릉", category="preference", title="기본 날씨", source="voice")
        self.hub = ObservabilityHub(history_limit=20)
        self.backend = DashboardBackend(
            self.hub,
            memory_manager=self.memory,
            config_path=self.config_path,
            port=0,
        ).start()

    def tearDown(self):
        self.backend.stop()
        self.config_path.unlink(missing_ok=True)

    def get_json(self, path):
        with urlopen(self.backend.url + path, timeout=2) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_event_bridge_drives_runtime_and_event_api(self):
        bridge = DashboardEventBridge(self.hub)
        bridge.handle_event(
            JarvisEvent(
                event_type=JarvisEventType.STATUS_CHANGED,
                state=JarvisState(status=JarvisStatus.THINKING, message="Planning"),
            )
        )
        events = self.get_json("/api/events")
        self.assertEqual(events[-1]["type"], "jarvis.status.changed")
        self.assertEqual(self.get_json("/api/status")["runtime"]["status"], "THINKING")

    def test_runtime_lock_owner_is_projected(self):
        self.hub.record(
            "runtime.lock.acquired",
            {"owner": "dashboard", "queued": 2},
        )
        runtime = self.get_json("/api/status")["runtime"]
        self.assertEqual(runtime["turn_owner"], "DASHBOARD")
        self.assertTrue(runtime["turn_busy"])
        self.assertEqual(runtime["turn_queued"], 2)

        self.hub.record(
            "runtime.lock.released",
            {"owner": "dashboard", "queued": 0},
        )
        runtime = self.get_json("/api/status")["runtime"]
        self.assertEqual(runtime["turn_owner"], "")
        self.assertFalse(runtime["turn_busy"])

    def test_language_context_is_projected_to_runtime_status(self):
        self.hub.record(
            "runtime.language.resolved",
            {
                "detected_language": "ja",
                "response_language": "ja",
                "policy": "AUTO",
                "confidence": 0.99,
                "tts_voice": "openai:nova:ja",
                "stt_provider": "openai",
            },
        )

        runtime = self.get_json("/api/status")["runtime"]

        self.assertEqual(runtime["detected_language"], "ja")
        self.assertEqual(runtime["response_language"], "ja")
        self.assertEqual(runtime["tts_voice"], "openai:nova:ja")

    def test_language_override_events_are_projected_to_runtime_status(self):
        self.hub.record(
            "runtime.language.override_set",
            {"override_language": "en"},
        )
        runtime = self.get_json("/api/status")["runtime"]
        self.assertTrue(runtime["language_override"])
        self.assertEqual(runtime["override_language"], "en")

        self.hub.record(
            "runtime.language.override_cleared",
            {"previous_language": "en"},
        )
        runtime = self.get_json("/api/status")["runtime"]
        self.assertFalse(runtime["language_override"])
        self.assertEqual(runtime["override_language"], "")

    def test_memory_can_be_viewed_and_deleted(self):
        memories = self.get_json("/api/memory")
        self.assertEqual(memories[0]["content"], "강릉")
        stats = self.get_json("/api/memory/stats")
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["types"]["preference"], 1)
        request = Request(self.backend.url + "/api/memory/" + memories[0]["id"], method="DELETE")
        with urlopen(request, timeout=2) as response:
            self.assertTrue(json.loads(response.read())["deleted"])
        self.assertEqual(self.get_json("/api/memory"), [])

    def test_settings_read_write_and_secret_guard(self):
        request = Request(
            self.backend.url + "/api/settings",
            data=json.dumps({"provider": "openai", "debug": True}).encode(),
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=2):
            pass
        self.assertTrue(self.get_json("/api/settings")["debug"])
        request = Request(
            self.backend.url + "/api/settings",
            data=json.dumps({"api_key": "never"}).encode(),
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=2)
        self.assertEqual(raised.exception.code, 400)
        raised.exception.close()

    def test_log_filter(self):
        self.hub.record("PlannerStarted", {"goal": "weather"})
        self.hub.record("ProviderFailed", {"reason": "offline"}, level="ERROR")
        logs = self.get_json("/api/logs?level=ERROR&q=offline")
        self.assertEqual([item["message"] for item in logs], ["ProviderFailed"])

    def test_task_lifecycle_is_projected_from_core_event_trace(self):
        self.hub.record(
            "event.publish",
            {"event_type": "TaskStarted", "aggregate_id": "RT-123", "goal": "weather"},
        )
        task = self.get_json("/api/tasks")[0]
        self.assertEqual(task["id"], "RT-123")
        self.assertEqual(task["status"], "RUNNING")

    def test_task_graph_validation_is_projected_for_dashboard(self):
        validation = {
            "graph_id": "GRAPH-1",
            "valid": False,
            "issues": [],
            "stages": [
                {"stage": "STRUCTURAL", "status": "PASS", "issues": []},
                {
                    "stage": "PERMISSION",
                    "status": "FAIL",
                    "issues": [
                        {
                            "code": "PERMISSION_CONFIRM_REQUIRED",
                            "message": "Confirm Required",
                            "node_id": "STEP-1-CALENDAR",
                            "blocking": True,
                            "stage": "PERMISSION",
                            "details": {
                                "reason": "Confirm Required",
                                "ability": "DeleteFile",
                                "risk": "restricted",
                            },
                        }
                    ],
                },
            ],
        }
        self.hub.record(
            "runtime.task_graph.validated",
            {
                "graph_id": "GRAPH-1",
                "task_id": "RT-1",
                "validation": validation,
                "graph": {
                    "graph_id": "GRAPH-1",
                    "task_id": "RT-1",
                    "nodes": [
                        {
                            "node_id": "STEP-1-CALENDAR",
                            "ability": "calendar",
                            "operation": "query",
                            "state": "PENDING",
                            "dependencies": [],
                            "output_types": {"result": "CalendarEvent"},
                        }
                    ],
                    "edges": [],
                },
            },
        )

        items = self.get_json("/api/task-graphs/validation")

        self.assertEqual(items["GRAPH-1"]["task_id"], "RT-1")
        self.assertEqual(items["GRAPH-1"]["stages"][1]["status"], "FAIL")
        self.assertEqual(
            items["GRAPH-1"]["nodes"]["STEP-1-CALENDAR"]["ability"],
            "calendar",
        )
        self.assertEqual(
            items["GRAPH-1"]["nodes"]["STEP-1-CALENDAR"]["permission"]["risk"],
            "restricted",
        )
        self.assertEqual(
            items["GRAPH-1"]["replay_events"][0]["type"],
            "runtime.task_graph.validated",
        )
        self.assertEqual(
            items["GRAPH-1"]["lifecycle"]["validation"]["status"],
            "FAILED",
        )

    def test_task_graph_execution_result_and_memory_lifecycle_is_projected(self):
        self.hub.record(
            "runtime.task_graph.validated",
            {
                "graph_id": "GRAPH-LIFE",
                "task_id": "RT-LIFE",
                "valid": True,
                "validation": {
                    "graph_id": "GRAPH-LIFE",
                    "valid": True,
                    "issues": [],
                    "stages": [],
                },
            },
        )
        self.hub.record(
            "runtime.task_graph.checkpoint",
            {"graph_id": "GRAPH-LIFE", "task_id": "RT-LIFE", "state": "RUNNING"},
        )
        self.hub.record(
            "runtime.task_graph.node_result",
            {
                "graph_id": "GRAPH-LIFE",
                "task_id": "RT-LIFE",
                "result_status": "COMPLETED",
                "memory_ref_count": 2,
                "provider": "openweather",
                "provider_latency_ms": 132,
            },
        )
        self.hub.record(
            "runtime.task_graph.tts",
            {
                "graph_id": "GRAPH-LIFE",
                "task_id": "RT-LIFE",
                "status": "COMPLETED",
                "provider": "openai",
                "latency_ms": 284,
            },
        )

        lifecycle = self.hub.snapshot()["task_graph_validations"]["GRAPH-LIFE"]["lifecycle"]

        self.assertEqual(lifecycle["validation"]["status"], "COMPLETED")
        self.assertEqual(lifecycle["execution"]["status"], "RUNNING")
        self.assertEqual(lifecycle["provider"]["status"], "COMPLETED")
        self.assertEqual(lifecycle["provider"]["provider"], "openweather")
        self.assertEqual(lifecycle["provider"]["latency_ms"], 132)
        self.assertEqual(lifecycle["result"]["status"], "COMPLETED")
        self.assertEqual(lifecycle["memory_updated"]["status"], "COMPLETED")
        self.assertEqual(lifecycle["memory_updated"]["count"], 2)
        self.assertEqual(lifecycle["tts"]["status"], "COMPLETED")
        self.assertEqual(lifecycle["tts"]["provider"], "openai")
        metrics = self.hub.snapshot()["task_graph_validations"]["GRAPH-LIFE"]["metrics"]
        self.assertEqual(metrics["provider_ms"], 132.0)
        self.assertEqual(metrics["critical_path_ms"], 132.0)
        self.assertEqual(metrics["tts_ms"], 284.0)
        self.assertIn("total_ms", metrics)

    def test_shadow_comparison_and_running_node_are_projected(self):
        self.hub.record(
            "runtime.task_graph.shadow_compared",
            {
                "graph_id": "GRAPH-SHADOW",
                "plan_id": "RP-SHADOW",
                "equivalent": True,
                "checks": {"abilities": True},
                "mismatches": [],
            },
        )
        self.hub.record(
            "runtime.task_graph.node_started",
            {
                "graph_id": "GRAPH-SHADOW",
                "task_id": "RT-512",
                "node_id": "STEP-1-WEATHER",
                "ability": "weather",
                "action": "query",
            },
        )
        self.hub.record(
            "runtime.task_graph.node_result",
            {
                "graph_id": "GRAPH-SHADOW",
                "task_id": "RT-512",
                "node_id": "STEP-1-WEATHER",
                "result_status": "COMPLETED",
                "provider": "openweather",
                "provider_latency_ms": 132,
            },
        )

        item = self.hub.snapshot()["task_graph_validations"]["GRAPH-SHADOW"]

        self.assertTrue(item["plan_comparison"]["equivalent"])
        self.assertEqual(item["task_id"], "RT-512")
        node = item["nodes"]["STEP-1-WEATHER"]
        self.assertEqual(node["status"], "COMPLETED")
        self.assertTrue(node["started_at"])
        self.assertTrue(node["finished_at"])
        self.assertIsNotNone(node["duration_ms"])

    def test_uncorrelated_tts_does_not_complete_task_graph(self):
        self.hub.record(
            "runtime.task_graph.validated",
            {
                "graph_id": "GRAPH-TTS-WAIT",
                "task_id": "RT-TTS-WAIT",
                "valid": True,
                "validation": {"graph_id": "GRAPH-TTS-WAIT", "valid": True, "stages": []},
            },
        )
        self.hub.record(
            "voice.tts.playback.finished",
            {"playback_success": True},
        )

        lifecycle = self.hub.snapshot()["task_graph_validations"]["GRAPH-TTS-WAIT"]["lifecycle"]

        self.assertEqual(lifecycle["tts"]["status"], "WAITING")

    def test_semantic_registry_tree_is_available(self):
        payload = self.get_json("/api/semantic-types")
        names = {item["name"] for item in payload["types"]}

        self.assertIn("WeatherReport", names)
        self.assertTrue(payload["tree"])

    def test_metrics_count_runtime_categories(self):
        self.hub.record("voice.wake.state", {"state": "ready"})
        self.hub.record("planner.completed", {"steps": 1})
        self.hub.record("memory.retrieved", {"count": 1})
        self.hub.record("ability.completed", {"ability": "weather"})
        metrics = self.hub.snapshot()["metrics"]
        self.assertEqual(metrics["wake"], 1)
        self.assertEqual(metrics["planner"], 1)
        self.assertEqual(metrics["memory"], 1)
        self.assertEqual(metrics["ability"], 1)

    def test_provider_inventory_uses_configuration(self):
        providers = self.get_json("/api/providers")
        domains = {item["domain"]: item for item in providers}
        self.assertEqual(domains["Weather"]["provider"], "openweather")
        self.assertEqual(domains["TTS"]["status"], "ONLINE")

    def test_idle_scheduler_tick_is_log_only(self):
        queue = self.hub.subscribe()
        self.hub.record(
            "reminder.scheduler.tick",
            {"now": "2026-07-27T16:30:32", "due": 0},
        )
        snapshot = self.hub.snapshot()
        self.assertEqual(snapshot["events"], [])
        self.assertEqual(snapshot["metrics"]["events"], 0)
        self.assertEqual(snapshot["logs"][-1]["message"], "reminder.scheduler.tick")
        self.assertEqual(queue.get(timeout=1)["kind"], "log")

    def test_due_scheduler_tick_remains_visible(self):
        self.hub.record(
            "reminder.scheduler.tick",
            {"now": "2026-07-27T16:31:00", "due": 1},
        )
        self.assertEqual(self.hub.snapshot()["events"][-1]["type"], "reminder.scheduler.tick")

    def test_websocket_event_includes_updated_runtime_projection(self):
        queue = self.hub.subscribe()

        self.hub.record(
            "runtime.language.resolved",
            {
                "detected_language": "ja",
                "response_language": "ja",
                "policy": "AUTO",
                "tts_voice": "openai:nova:ja",
            },
        )

        message = queue.get(timeout=1)
        self.assertEqual(message["kind"], "event")
        self.assertEqual(message["runtime"]["detected_language"], "ja")
        self.assertEqual(message["runtime"]["response_language"], "ja")
        self.assertEqual(message["runtime"]["tts_voice"], "openai:nova:ja")

    def test_weather_location_resolution_is_projected_for_dashboard(self):
        self.hub.record(
            "weather.location.resolved",
            {
                "provider_query": "Sapporo,JP",
                "resolution_source": "geocoding",
                "latitude": 43.0618,
                "longitude": 141.3545,
            },
        )

        runtime = self.hub.snapshot()["runtime"]
        self.assertEqual(runtime["weather_location"], "Sapporo,JP")
        self.assertEqual(runtime["weather_location_source"], "geocoding")
        self.assertEqual(
            runtime["weather_location_coordinates"],
            "43.0618,141.3545",
        )

    def test_ability_latency_is_projected_from_dispatcher(self):
        self.hub.record(
            "dispatcher.result",
            {"selected": "weather", "success": True, "duration_ms": 132},
        )
        metric = self.hub.snapshot()["ability_metrics"]["weather"]
        self.assertEqual(metric["latency_ms"], 132)
        self.assertTrue(metric["success"])


if __name__ == "__main__":
    unittest.main()
