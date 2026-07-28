"""Thread-safe runtime observations shared by HTTP and WebSocket clients."""

from collections import deque
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from queue import Queue
from threading import RLock
from uuid import uuid4


def _json_value(value):
    if is_dataclass(value):
        return {key: _json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _elapsed_ms(started_at, finished_at):
    try:
        started = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        finished = datetime.fromisoformat(str(finished_at).replace("Z", "+00:00"))
        return round(max(0.0, (finished - started).total_seconds() * 1000), 3)
    except (TypeError, ValueError):
        return None


def _task_graph_metrics(item):
    stages = list(item.get("stages", []))
    nodes = list(dict(item.get("nodes", {})).values())
    lifecycle = dict(item.get("lifecycle", {}))
    events = list(item.get("replay_events", []))
    validation_ms = round(
        sum(float(stage.get("duration_ms", 0) or 0) for stage in stages),
        3,
    )
    provider_ms = round(
        sum(float(node.get("duration_ms", node.get("latency_ms", 0)) or 0) for node in nodes),
        3,
    )
    tts_ms = float(lifecycle.get("tts", {}).get("latency_ms", 0) or 0)
    memory_ms = round(
        sum(float(event.get("memory_latency_ms", 0) or 0) for event in events),
        3,
    )
    total_ms = (
        _elapsed_ms(events[0]["timestamp"], events[-1]["timestamp"])
        if len(events) > 1
        else 0.0
    )
    node_by_id = {str(node.get("node_id") or ""): node for node in nodes}
    path_cache = {}

    def longest_path(node_id, visiting=None):
        if node_id in path_cache:
            return path_cache[node_id]
        visiting = set(visiting or ())
        if node_id in visiting:
            return 0.0
        visiting.add(node_id)
        node = node_by_id.get(node_id, {})
        own = float(node.get("duration_ms", node.get("latency_ms", 0)) or 0)
        upstream = max(
            (
                longest_path(str(dependency), visiting)
                for dependency in node.get("dependencies", [])
            ),
            default=0.0,
        )
        path_cache[node_id] = own + upstream
        return path_cache[node_id]

    critical_path_ms = round(
        max((longest_path(node_id) for node_id in node_by_id), default=0.0),
        3,
    )
    parallel_efficiency = (
        round(critical_path_ms / provider_ms, 4)
        if provider_ms > 0
        else None
    )
    provider_concurrency = (
        round(provider_ms / total_ms, 4)
        if total_ms is not None and total_ms > 0
        else None
    )
    return {
        "validation_ms": validation_ms,
        "provider_ms": provider_ms,
        "critical_path_ms": critical_path_ms,
        "parallel_efficiency": parallel_efficiency,
        "provider_concurrency": provider_concurrency,
        "tts_ms": round(tts_ms, 3),
        "memory_ms": memory_ms,
        "total_ms": total_ms,
    }


class ObservabilityHub:
    """Keep a bounded, queryable view of what Jarvis is doing now."""

    def __init__(self, history_limit=2000):
        self.started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        self.events = deque(maxlen=history_limit)
        self.logs = deque(maxlen=history_limit)
        self.tasks = {}
        self.task_graph_validations = {}
        self.ability_metrics = {}
        self.metrics = {
            "events": 0,
            "memory": 0,
            "tasks": 0,
            "wake": 0,
            "planner": 0,
            "ability": 0,
        }
        self.runtime = {
            "status": "ONLINE",
            "wake": "READY",
            "voice": "idle",
            "current_session": "",
            "current_task": "",
            "planner": "idle",
            "current_ability": "",
            "current_provider": "",
            "wake_method": "unknown",
            "turn_owner": "",
            "turn_state": "",
            "turn_started_at": "",
            "turn_timeout": "",
            "turn_soft_timeout": "",
            "turn_hard_timeout": "",
            "turn_priority": 0,
            "turn_priority_name": "",
            "turn_source": "",
            "turn_conversation_id": "",
            "turn_id": "",
            "turn_task_id": "",
            "turn_step_id": "",
            "turn_busy": False,
            "turn_queued": 0,
            "turn_queue": [],
            "detected_language": "",
            "conversation_language": "",
            "response_language": "",
            "language_response_source": "",
            "language_policy": "AUTO",
            "language_confidence": 0.0,
            "tts_voice": "",
            "stt_provider": "",
            "language_override": False,
            "override_language": "",
            "weather_location": "",
            "weather_location_source": "",
            "weather_location_coordinates": "",
        }
        self._subscribers = set()
        self._lock = RLock()

    def record(self, event_type, payload=None, category=None, level="INFO"):
        name = getattr(event_type, "value", event_type)
        name = str(name)
        body = _json_value(payload or {})
        observation = {
            "id": uuid4().hex,
            "type": name,
            "category": category or self._category(name, body),
            "level": str(level).upper(),
            "timestamp": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "payload": body,
        }
        background = self._is_background_heartbeat(name, body)
        log_entry = {
            "id": observation["id"],
            "timestamp": observation["timestamp"],
            "level": observation["level"],
            "source": observation["category"],
            "message": name,
            "details": body,
        }
        with self._lock:
            self.logs.append(log_entry)
            if not background:
                self.events.append(observation)
                self._increment_metrics(observation)
                self._apply_runtime(observation)
                self._apply_task_event(observation)
                self._apply_task_graph_validation(observation)
                self._apply_ability_latency(observation)
            subscribers = tuple(self._subscribers)
            runtime = _json_value(self.runtime)
        message = {
            "kind": "log" if background else "event",
            "data": log_entry if background else observation,
            "runtime": runtime,
        }
        for subscriber in subscribers:
            subscriber.put(message)
        return observation

    def record_task(self, task):
        data = task.to_dict() if hasattr(task, "to_dict") else _json_value(task)
        task_id = str(data.get("id", ""))
        if task_id:
            with self._lock:
                self.tasks[task_id] = data
                self.runtime["current_task"] = task_id
            self.record("TaskUpdated", data, category="task")
        return data

    def subscribe(self):
        queue = Queue(maxsize=256)
        with self._lock:
            self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue):
        with self._lock:
            self._subscribers.discard(queue)

    def snapshot(self):
        with self._lock:
            return {
                "started_at": self.started_at,
                "runtime": dict(self.runtime),
                "events": list(self.events),
                "logs": list(self.logs),
                "tasks": list(self.tasks.values()),
                "task_graph_validations": dict(self.task_graph_validations),
                "metrics": dict(self.metrics),
                "ability_metrics": dict(self.ability_metrics),
            }

    def _apply_runtime(self, observation):
        name = observation["type"].lower()
        payload = observation["payload"]
        state = payload.get("state", payload) if isinstance(payload, dict) else {}
        if not isinstance(state, dict):
            state = {"state": state}
        status = state.get("status") if isinstance(state, dict) else None
        if name == "runtime.state.changed":
            status = state.get("state")
        if name == "runtime.lock.acquired":
            self.runtime["turn_owner"] = str(state.get("owner", "")).upper()
            self.runtime["turn_state"] = str(state.get("state", "")).upper()
            self.runtime["turn_started_at"] = str(state.get("started_at", ""))
            self.runtime["turn_timeout"] = state.get("timeout") or ""
            self.runtime["turn_soft_timeout"] = state.get("soft_timeout") or ""
            self.runtime["turn_hard_timeout"] = state.get("hard_timeout") or ""
            self.runtime["turn_priority"] = int(state.get("priority", 0) or 0)
            self.runtime["turn_priority_name"] = str(state.get("priority_name", ""))
            self.runtime["turn_source"] = str(state.get("source", ""))
            self.runtime["turn_conversation_id"] = str(state.get("conversation_id", ""))
            self.runtime["turn_id"] = str(state.get("turn_id", ""))
            self.runtime["turn_task_id"] = str(state.get("task_id", ""))
            self.runtime["turn_step_id"] = str(state.get("step_id", ""))
            self.runtime["turn_busy"] = True
            self.runtime["turn_queued"] = int(state.get("queued", 0) or 0)
            self.runtime["turn_queue"] = list(state.get("queue", []) or [])
        elif name == "runtime.lock.released":
            self.runtime["turn_owner"] = ""
            self.runtime["turn_state"] = str(state.get("state", "")).upper()
            self.runtime["turn_busy"] = False
            self.runtime["turn_queued"] = int(state.get("queued", 0) or 0)
            self.runtime["turn_queue"] = list(state.get("queue", []) or [])
        elif name in {"runtime.lock.busy", "runtime.lock.queued"}:
            self.runtime["turn_owner"] = str(state.get("owner", "")).upper()
            self.runtime["turn_busy"] = True
            self.runtime["turn_queued"] = int(state.get("queued", 0) or 0)
            self.runtime["turn_queue"] = list(state.get("queue", []) or [])
        elif name == "runtime.turn.preempt_requested":
            self.runtime["turn_state"] = "INTERRUPTING"
        elif name == "runtime.turn.timeout_warning":
            self.runtime["turn_state"] = "TIMEOUT_WARNING"
        elif name == "runtime.turn.timeout":
            self.runtime["turn_state"] = "INTERRUPTING"
        elif name == "runtime.language.resolved":
            self.runtime["detected_language"] = str(
                state.get("detected_language", "")
            )
            self.runtime["conversation_language"] = str(
                state.get("conversation_language", "")
            )
            self.runtime["response_language"] = str(
                state.get("response_language", "")
            )
            self.runtime["language_response_source"] = str(
                state.get("response_source", "")
            )
            self.runtime["language_policy"] = str(state.get("policy", "AUTO"))
            self.runtime["language_confidence"] = float(
                state.get("confidence", 0) or 0
            )
            self.runtime["tts_voice"] = str(state.get("tts_voice", ""))
            self.runtime["stt_provider"] = str(state.get("stt_provider", ""))
        elif name == "runtime.language.override_set":
            self.runtime["language_override"] = True
            self.runtime["override_language"] = str(
                state.get("override_language", "")
            )
        elif name == "runtime.language.override_cleared":
            self.runtime["language_override"] = False
            self.runtime["override_language"] = ""
        elif name == "weather.location.resolved":
            self.runtime["weather_location"] = str(
                state.get("provider_query")
                or state.get("location_canonical")
                or ""
            )
            self.runtime["weather_location_source"] = str(
                state.get("resolution_source", "")
            )
            latitude = state.get("latitude")
            longitude = state.get("longitude")
            self.runtime["weather_location_coordinates"] = (
                f"{latitude},{longitude}"
                if latitude is not None and longitude is not None
                else ""
            )
        if status:
            self.runtime["status"] = str(status).upper()
        if "wake" in name:
            self.runtime["wake"] = str(state.get("status", state.get("state", "READY"))).upper()
            self.runtime["voice"] = "wake"
        elif "stt" in name or "listen" in name:
            self.runtime["voice"] = "listening"
        elif "tts" in name:
            self.runtime["voice"] = "speaking" if "start" in name else "idle"
        if "planner" in name:
            self.runtime["planner"] = name.rsplit(".", 1)[-1]
        if "ability" in name or "tool" in name:
            self.runtime["current_ability"] = str(
                state.get("ability", state.get("tool", state.get("name", "")))
            )

    def _apply_task_event(self, observation):
        name = observation["type"]
        payload = observation["payload"]
        nested_type = str(payload.get("event_type", "")) if isinstance(payload, dict) else ""
        if "task" not in name.lower() and "task" not in nested_type.lower():
            return
        task_id = str(
            payload.get("task_id")
            or payload.get("aggregate_id")
            or payload.get("id")
            or ""
        )
        if not task_id:
            return
        current = dict(self.tasks.get(task_id, {"id": task_id, "goal": "", "current_step": 0}))
        current.update({key: value for key, value in payload.items() if value not in ("", None)})
        lifecycle = nested_type or name
        if "started" in lifecycle.lower():
            current["status"] = "RUNNING"
        elif "completed" in lifecycle.lower():
            current["status"] = "COMPLETED"
        elif "failed" in lifecycle.lower():
            current["status"] = "FAILED"
        self.tasks[task_id] = current
        self.runtime["current_task"] = task_id

    def _apply_task_graph_validation(self, observation):
        event_name = observation["type"].lower()
        graph_tts_event = (
            event_name in {
                "runtime.task_graph.tts",
                "voice.tts.playback.started",
                "voice.tts.playback.finished",
                "voice.tts.playback.completed",
                "voice.tts.playback.failed",
            }
            and bool(observation["payload"].get("graph_id"))
        )
        if event_name not in {
            "runtime.task_graph.shadow_compared",
            "runtime.task_graph.validated",
            "runtime.task_graph.checkpoint",
            "runtime.task_graph.node_started",
            "runtime.task_graph.node_result",
        } and not graph_tts_event:
            return
        payload = observation["payload"]
        validation = payload.get("validation", {})
        graph_id = str(payload.get("graph_id") or validation.get("graph_id") or "")
        if not graph_id:
            return
        item = dict(self.task_graph_validations.get(graph_id, {}))
        if validation:
            item.update(validation)
        graph = payload.get("graph", {})
        if graph:
            item["graph"] = dict(graph)
            item["nodes"] = {
                str(node.get("node_id") or ""): dict(node)
                for node in graph.get("nodes", [])
            }
            item["edges"] = list(graph.get("edges", []))
            permission_by_node = {}
            for stage in validation.get("stages", []):
                if str(stage.get("stage") or "").upper() != "PERMISSION":
                    continue
                for issue in stage.get("issues", []):
                    node_id = str(issue.get("node_id") or "")
                    details = dict(issue.get("details") or {})
                    if node_id:
                        permission_by_node[node_id] = {
                            "status": str(issue.get("code") or ""),
                            "risk": str(details.get("risk") or "unknown"),
                            "reason": str(details.get("reason") or issue.get("message") or ""),
                        }
            for node_id, permission in permission_by_node.items():
                if node_id in item["nodes"]:
                    item["nodes"][node_id]["permission"] = permission
        item["graph_id"] = graph_id
        item["task_id"] = str(payload.get("task_id") or item.get("task_id") or "")
        item["timestamp"] = observation["timestamp"]
        lifecycle = dict(item.get("lifecycle", {}))
        if event_name == "runtime.task_graph.shadow_compared":
            item["plan_comparison"] = {
                "plan_id": str(payload.get("plan_id") or ""),
                "equivalent": bool(payload.get("equivalent")),
                "checks": dict(payload.get("checks") or {}),
                "mismatches": list(payload.get("mismatches") or []),
            }
        elif event_name == "runtime.task_graph.validated":
            lifecycle["validation"] = {
                "status": "COMPLETED" if bool(payload.get("valid")) else "FAILED",
                "timestamp": observation["timestamp"],
            }
            lifecycle.setdefault("execution", {"status": "WAITING", "timestamp": ""})
            lifecycle.setdefault("provider", {"status": "WAITING", "timestamp": ""})
            lifecycle.setdefault("result", {"status": "WAITING", "timestamp": ""})
            lifecycle.setdefault("memory_updated", {"status": "WAITING", "timestamp": ""})
            lifecycle.setdefault("tts", {"status": "WAITING", "timestamp": ""})
        elif event_name == "runtime.task_graph.checkpoint":
            graph_state = str(payload.get("state") or "").upper()
            item["graph_state"] = graph_state
            lifecycle["execution"] = {
                "status": (
                    "COMPLETED"
                    if graph_state in {"COMPLETED", "PARTIAL_SUCCESS"}
                    else "FAILED"
                    if graph_state in {"FAILED", "CANCELLED"}
                    else "RUNNING"
                ),
                "timestamp": observation["timestamp"],
            }
        elif event_name == "runtime.task_graph.node_started":
            nodes = dict(item.get("nodes", {}))
            node_id = str(payload.get("node_id") or "")
            node = dict(nodes.get(node_id, {}))
            node.update(
                {
                    "node_id": node_id,
                    "ability": str(payload.get("ability") or node.get("ability") or ""),
                    "action": str(payload.get("action") or node.get("operation") or ""),
                    "status": "RUNNING",
                    "started_at": observation["timestamp"],
                    "timestamp": observation["timestamp"],
                }
            )
            nodes[node_id] = node
            item["nodes"] = nodes
            lifecycle["execution"] = {
                "status": "RUNNING",
                "timestamp": observation["timestamp"],
            }
        elif event_name == "runtime.task_graph.node_result":
            result_status = str(payload.get("result_status") or "").upper()
            provider = str(payload.get("provider") or "")
            nodes = dict(item.get("nodes", {}))
            node_id = str(payload.get("node_id") or "")
            node = dict(nodes.get(node_id, {}))
            started_at = str(node.get("started_at") or "")
            finished_at = observation["timestamp"]
            measured_duration = _elapsed_ms(started_at, finished_at)
            node.update(
                {
                    "node_id": node_id,
                    "status": result_status or "COMPLETED",
                    "provider": provider,
                    "latency_ms": payload.get("provider_latency_ms"),
                    "duration_ms": (
                        measured_duration
                        if measured_duration is not None
                        else payload.get("provider_latency_ms")
                    ),
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "output_types": dict(payload.get("output_types") or node.get("output_types") or {}),
                    "dependencies": list(payload.get("dependencies") or node.get("dependencies") or []),
                    "timestamp": observation["timestamp"],
                }
            )
            nodes[node_id] = node
            item["nodes"] = nodes
            lifecycle["provider"] = {
                "status": "COMPLETED" if provider else "NO_DATA",
                "timestamp": observation["timestamp"],
                "provider": provider,
                "latency_ms": payload.get("provider_latency_ms"),
            }
            lifecycle["result"] = {
                "status": result_status or "COMPLETED",
                "timestamp": observation["timestamp"],
            }
            memory_count = int(payload.get("memory_ref_count", 0) or 0)
            lifecycle["memory_updated"] = {
                "status": "COMPLETED" if memory_count else "NO_CHANGE",
                "timestamp": observation["timestamp"],
                "count": memory_count,
            }
        elif graph_tts_event:
            raw_status = str(payload.get("status") or "").upper()
            if not raw_status:
                raw_status = (
                    "FAILED"
                    if "failed" in event_name
                    else "RUNNING"
                    if "started" in event_name
                    else "COMPLETED"
                )
            lifecycle["tts"] = {
                "status": raw_status,
                "timestamp": observation["timestamp"],
                "provider": str(payload.get("provider") or ""),
                "latency_ms": payload.get("latency_ms"),
                "error": str(payload.get("error") or ""),
            }
        item["lifecycle"] = lifecycle
        replay_events = list(item.get("replay_events", []))
        replay_events.append(
            {
                "timestamp": observation["timestamp"],
                "type": observation["type"],
                "node_id": str(payload.get("node_id") or ""),
                "state": str(
                    payload.get("result_status")
                    or payload.get("node_state")
                    or payload.get("state")
                    or payload.get("status")
                    or ""
                ),
                "provider": str(payload.get("provider") or ""),
                "latency_ms": payload.get("provider_latency_ms", payload.get("latency_ms")),
                "memory_latency_ms": payload.get("memory_latency_ms"),
            }
        )
        item["replay_events"] = replay_events[-200:]
        item["metrics"] = _task_graph_metrics(item)
        self.task_graph_validations[graph_id] = item

    def _increment_metrics(self, observation):
        self.metrics["events"] += 1
        category = observation["category"]
        name = observation["type"].lower()
        nested = str(observation["payload"].get("event_type", "")).lower()
        combined = f"{name} {nested}"
        if category == "memory":
            self.metrics["memory"] += 1
        if category == "wake":
            self.metrics["wake"] += 1
        if category == "planner":
            self.metrics["planner"] += 1
        if category in {"ability", "tool"} or "ability" in combined or "tool" in combined:
            self.metrics["ability"] += 1
        if "taskstarted" in combined or "task.started" in combined:
            self.metrics["tasks"] += 1

    def _apply_ability_latency(self, observation):
        name = observation["type"].lower()
        payload = observation["payload"]
        if name not in {"dispatcher.result", "ability.completed", "tool.completed"}:
            return
        ability = str(
            payload.get("selected")
            or payload.get("ability")
            or payload.get("tool")
            or payload.get("tool_name")
            or payload.get("intent")
            or ""
        ).strip()
        if not ability:
            return
        latency = None
        for key in ("duration_ms", "latency_ms", "elapsed_ms"):
            if key in payload:
                try:
                    latency = int(float(payload[key]))
                except (TypeError, ValueError):
                    latency = None
                break
        self.ability_metrics[ability] = {
            "latency_ms": latency,
            "success": bool(payload.get("success", True)),
            "last_call": observation["timestamp"],
        }

    @staticmethod
    def _is_background_heartbeat(name, payload):
        if str(name).lower() != "reminder.scheduler.tick":
            return False
        try:
            return int((payload or {}).get("due", 0) or 0) == 0
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _category(name, payload=None):
        lowered = f"{name} {str((payload or {}).get('event_type', ''))}".lower()
        for category in (
            "wake",
            "planner",
            "memory",
            "permission",
            "voice",
            "plugin",
            "scheduler",
            "task",
            "ability",
            "tool",
        ):
            if category in lowered:
                return category
        if "stt" in lowered or "tts" in lowered:
            return "voice"
        return "runtime"


class DashboardEventBridge:
    """Adapt both Jarvis event shapes into normalized observations."""

    def __init__(self, hub):
        self.hub = hub

    def handle_event(self, event):
        event_type = getattr(event, "event_type", getattr(event, "name", type(event).__name__))
        if hasattr(event, "to_dict"):
            payload = event.to_dict()
        elif is_dataclass(event):
            payload = asdict(event)
        else:
            payload = getattr(event, "__dict__", {"value": str(event)})
        return self.hub.record(event_type, payload)
