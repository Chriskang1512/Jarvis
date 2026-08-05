"""Dependency-free local Dashboard HTTP and WebSocket backend."""

import base64
import hashlib
import json
import struct
from dataclasses import asdict, is_dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Empty
from threading import Event, Lock, Thread
from urllib.parse import parse_qs, urlparse

from jarvis.runtime.turn_lock import RuntimeBusyError
from jarvis.runtime.task import DEFAULT_SEMANTIC_REGISTRY


STATIC_ROOT = Path(__file__).with_name("static")


class DashboardBackend:
    """Expose runtime observations without coupling Jarvis core to the UI."""

    def __init__(
        self,
        hub,
        memory_manager=None,
        diagnostics_collector=None,
        config_path="config.json",
        plugin_registry=None,
        ability_registry=None,
        runtime_service=None,
        semantic_registry=None,
        artifact_repository=None,
        projection_repository=None,
        projection_engine=None,
        host="127.0.0.1",
        port=8765,
    ):
        self.hub = hub
        self.memory_manager = memory_manager
        self.diagnostics_collector = diagnostics_collector
        self.config_path = Path(config_path)
        self.plugin_registry = plugin_registry
        self.ability_registry = ability_registry
        self.runtime_service = runtime_service
        self.semantic_registry = semantic_registry or DEFAULT_SEMANTIC_REGISTRY
        self.artifact_repository = artifact_repository
        self.projection_repository = projection_repository
        self.projection_engine = projection_engine
        self.host = host
        self.port = int(port)
        self.server = None
        self.thread = None

    @property
    def url(self):
        port = self.server.server_port if self.server else self.port
        return f"http://{self.host}:{port}"

    def start(self, background=True):
        backend = self

        class Handler(DashboardRequestHandler):
            dashboard = backend

        self.server = ThreadingHTTPServer((self.host, self.port), Handler)
        self.server.daemon_threads = True
        if background:
            self.thread = Thread(target=self.server.serve_forever, name="jarvis-dashboard", daemon=True)
            self.thread.start()
        else:
            self.server.serve_forever()
        return self

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None

    def memories(self, query=""):
        if self.memory_manager is None:
            return []
        if hasattr(self.memory_manager, "retrieve"):
            context = self.memory_manager.retrieve(query=query, limit=200)
            items = list(getattr(context, "records", ()))
        else:
            items = self.memory_manager.search(query) if query else self.memory_manager.store.list()
        return [item.to_dict() if hasattr(item, "to_dict") else item for item in items]

    def delete_memory(self, memory_id):
        if self.memory_manager is None:
            return False
        if hasattr(self.memory_manager, "retrieve"):
            records = getattr(self.memory_manager.retrieve(query="", limit=1000), "records", ())
            record = next((item for item in records if str(getattr(item, "id", "")) == str(memory_id)), None)
            if record is None:
                return False
            return bool(self.memory_manager.delete(record.key, record.memory_type))
        return bool(self.memory_manager.delete(memory_id))

    def artifacts(self, query="", **criteria):
        if self.artifact_repository is None:
            return []
        criteria = {key: value for key, value in criteria.items() if value}
        criteria["query"] = query
        items = self.artifact_repository.search_metadata(limit=200, **criteria)
        from jarvis.artifacts import artifact_to_dict

        return [artifact_to_dict(item) for item in items]

    def artifact(self, artifact_id):
        if self.artifact_repository is None:
            return None
        item = self.artifact_repository.get(artifact_id, include_deleted=True)
        if item is None:
            return None
        from jarvis.artifacts import artifact_to_dict

        return artifact_to_dict(item)

    def config(self):
        if not self.config_path.exists():
            return {}
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def save_config(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Settings must be a JSON object.")
        if any(_is_secret_key(key) for key in _walk_keys(payload)):
            raise ValueError("Secrets and credential paths cannot be edited from Dashboard.")
        self.config_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self.hub.record("SettingsUpdated", {"keys": sorted(payload)}, category="settings")
        return payload


class DashboardRequestHandler(BaseHTTPRequestHandler):
    dashboard = None
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/ws":
            return self._websocket()
        if parsed.path == "/api/status":
            snapshot = self.dashboard.hub.snapshot()
            return self._json({"runtime": snapshot["runtime"], "started_at": snapshot["started_at"]})
        if parsed.path == "/api/events":
            return self._json(self.dashboard.hub.snapshot()["events"])
        if parsed.path == "/api/tasks":
            return self._json(self.dashboard.hub.snapshot()["tasks"])
        if parsed.path == "/api/runtime/sessions/running":
            return self._json(self._projection_sessions(running=True))
        if parsed.path == "/api/runtime/sessions/recent":
            params = parse_qs(parsed.query)
            limit = int(params.get("limit", ["20"])[0])
            return self._json(self._projection_sessions(limit=limit))
        if parsed.path == "/api/runtime/statistics":
            engine = self.dashboard.projection_engine
            return self._json(engine.statistics() if engine else {})
        if parsed.path == "/api/runtime/projection-health":
            health = getattr(self.dashboard.projection_engine, "health", None)
            if health is None:
                return self._json({})
            payload = asdict(health)
            payload["status"] = health.status.value
            return self._json(payload)
        if parsed.path.startswith("/api/runtime/sessions/"):
            suffix = parsed.path[len("/api/runtime/sessions/"):]
            timeline = suffix.endswith("/timeline")
            session_id = suffix[:-len("/timeline")] if timeline else suffix
            repository = self.dashboard.projection_repository
            session = repository.get_session(session_id) if repository else None
            if session is None:
                return self._json({"error": "Session not found"}, 404)
            from jarvis.dashboard.projection_serialization import (
                session_to_dict,
                timeline_to_dict,
            )
            return self._json(
                [timeline_to_dict(item) for item in session.timeline]
                if timeline else session_to_dict(session)
            )
        if parsed.path == "/api/task-graphs/validation":
            return self._json(
                self.dashboard.hub.snapshot().get("task_graph_validations", {})
            )
        if parsed.path == "/api/semantic-types":
            return self._json(
                {
                    "types": [
                        {
                            "name": item.name,
                            "parents": list(item.parents),
                            "aliases": list(item.aliases),
                            "description": item.description,
                        }
                        for item in self.dashboard.semantic_registry.list()
                    ],
                    "tree": self.dashboard.semantic_registry.to_tree(),
                }
            )
        if parsed.path == "/api/logs":
            params = parse_qs(parsed.query)
            query = params.get("q", [""])[0].lower()
            level = params.get("level", [""])[0].upper()
            logs = self.dashboard.hub.snapshot()["logs"]
            if query:
                logs = [item for item in logs if query in json.dumps(item, ensure_ascii=False).lower()]
            if level:
                logs = [item for item in logs if item["level"] == level]
            return self._json(logs)
        if parsed.path == "/api/memory":
            query = parse_qs(parsed.query).get("q", [""])[0]
            return self._json(self.dashboard.memories(query))
        if parsed.path == "/api/memory/stats":
            return self._json(_memory_stats(self.dashboard.memories()))
        if parsed.path == "/api/artifacts":
            params = parse_qs(parsed.query)
            return self._json(
                self.dashboard.artifacts(
                    params.get("q", [""])[0],
                    artifact_type=params.get("type", [""])[0],
                    tag=params.get("tag", [""])[0],
                    goal_id=params.get("goal", [""])[0],
                    execution_id=params.get("execution", [""])[0],
                )
            )
        if parsed.path == "/api/artifacts/stats":
            items = self.dashboard.artifacts()
            counts = {}
            for item in items:
                key = item["artifactType"]
                counts[key] = counts.get(key, 0) + 1
            return self._json({"total": len(items), "byType": counts})
        if parsed.path.startswith("/api/artifacts/"):
            artifact_id = parsed.path.rsplit("/", 1)[-1]
            artifact = self.dashboard.artifact(artifact_id)
            return self._json(artifact) if artifact else self._json({"error": "Artifact not found"}, 404)
        if parsed.path == "/api/settings":
            return self._json(self.dashboard.config())
        if parsed.path == "/api/diagnostics":
            collector = self.dashboard.diagnostics_collector
            snapshot = collector.get_snapshot() if collector else {}
            if is_dataclass(snapshot):
                snapshot = asdict(snapshot)
            return self._json(snapshot)
        if parsed.path == "/api/plugins":
            return self._json(_registry_items(self.dashboard.plugin_registry, "list_plugins"))
        if parsed.path == "/api/abilities":
            return self._json(
                _ability_items(
                    self.dashboard.ability_registry,
                    self.dashboard.hub.snapshot().get("ability_metrics", {}),
                )
            )
        if parsed.path == "/api/providers":
            return self._json(_provider_items(self.dashboard))
        return self._static(parsed.path)

    def _projection_sessions(self, running=False, limit=20):
        repository = self.dashboard.projection_repository
        if repository is None:
            return []
        sessions = (
            repository.running_sessions()
            if running else repository.recent_sessions(limit=limit)
        )
        from jarvis.dashboard.projection_serialization import session_to_dict
        return [session_to_dict(item) for item in sessions]

    def do_PUT(self):
        if urlparse(self.path).path != "/api/settings":
            return self._json({"error": "Not found"}, 404)
        try:
            return self._json(self.dashboard.save_config(self._body_json()))
        except (ValueError, json.JSONDecodeError) as error:
            return self._json({"error": str(error)}, 400)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/memory/"):
            return self._json({"error": "Not found"}, 404)
        memory_id = path.rsplit("/", 1)[-1]
        if not self.dashboard.delete_memory(memory_id):
            return self._json({"error": "Memory not found"}, 404)
        self.dashboard.hub.record("MemoryDeleted", {"id": memory_id}, category="memory")
        return self._json({"deleted": True})

    def _body_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _static(self, path):
        filename = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (STATIC_ROOT / filename).resolve()
        if STATIC_ROOT.resolve() not in target.parents or not target.is_file():
            target = STATIC_ROOT / "index.html"
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
        }.get(target.suffix, "application/octet-stream")
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _websocket(self):
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            return self._json({"error": "WebSocket upgrade required"}, 400)
        accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
        ).decode()
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        queue = self.dashboard.hub.subscribe()
        closed = Event()
        send_lock = Lock()
        reader = Thread(
            target=self._websocket_reader,
            args=(closed, send_lock),
            name="jarvis-dashboard-input",
            daemon=True,
        )
        reader.start()
        try:
            self._send_ws({"kind": "snapshot", "data": self.dashboard.hub.snapshot()}, send_lock)
            while not closed.is_set():
                try:
                    self._send_ws(queue.get(timeout=1), send_lock)
                except Empty:
                    continue
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            closed.set()
            self.dashboard.hub.unsubscribe(queue)

    def _websocket_reader(self, closed, send_lock):
        try:
            while not closed.is_set():
                message = self._receive_ws()
                if message is None:
                    break
                self._handle_ws_message(message, send_lock)
        except (BrokenPipeError, ConnectionResetError, OSError, ValueError, json.JSONDecodeError):
            pass
        finally:
            closed.set()

    def _handle_ws_message(self, message, send_lock):
        runtime = self.dashboard.runtime_service
        message_type = str(message.get("type", ""))
        request_id = str(message.get("request_id", ""))
        if runtime is None:
            return self._send_ws(
                {"kind": "interaction.error", "request_id": request_id, "error": "Runtime is not connected."},
                send_lock,
            )
        self._send_ws(
            {"kind": "interaction.status", "request_id": request_id, "status": "processing"},
            send_lock,
        )
        try:
            if message_type == "tts.playback.finished":
                runtime.finish_browser_playback(
                    message.get("playback_token", ""),
                    reason="browser_playback_finished",
                )
                return self._send_ws(
                    {"kind": "interaction.status", "request_id": request_id, "status": "ready"},
                    send_lock,
                )
            if message_type == "input.text":
                result = runtime.submit_text(message.get("text", ""))
            elif message_type == "input.audio":
                audio = base64.b64decode(message.get("audio", ""), validate=True)
                result = runtime.submit_audio(audio, mime_type=message.get("mime_type", "audio/webm"))
            else:
                raise ValueError(f"Unsupported interaction type: {message_type}")
            self._send_ws(
                {
                    "kind": "interaction.result",
                    "request_id": request_id,
                    "text": result["text"],
                    "transcript": result.get("transcript", ""),
                    "audio": result.get("audio", ""),
                    "audio_mime": result.get("audio_mime", ""),
                    "input": result.get("input", {}),
                    "playback_token": result.get("playback_token", ""),
                    "session_id": result.get("session_id", ""),
                },
                send_lock,
            )
        except RuntimeBusyError as error:
            self._send_ws(
                {
                    "kind": "interaction.busy",
                    "request_id": request_id,
                    "owner": error.current_owner.value,
                    "requested_owner": error.requested_owner.value,
                    "error": str(error),
                },
                send_lock,
            )
        except Exception as error:
            self.dashboard.hub.record(
                "runtime.interaction.failed",
                {"request_id": request_id, "error": str(error)},
                level="ERROR",
            )
            self._send_ws(
                {"kind": "interaction.error", "request_id": request_id, "error": str(error)},
                send_lock,
            )

    def _receive_ws(self):
        first = self.rfile.read(2)
        if len(first) < 2:
            return None
        opcode = first[0] & 0x0F
        masked = bool(first[1] & 0x80)
        length = first[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8))[0]
        if length > 16 * 1024 * 1024:
            raise ValueError("WebSocket message exceeds 16 MB.")
        mask = self._read_exact(4) if masked else b""
        payload = bytearray(self._read_exact(length))
        if masked:
            for index in range(len(payload)):
                payload[index] ^= mask[index % 4]
        if opcode == 0x8:
            return None
        if opcode != 0x1:
            return {}
        return json.loads(payload.decode("utf-8"))

    def _read_exact(self, length):
        chunks = bytearray()
        while len(chunks) < length:
            chunk = self.rfile.read(length - len(chunks))
            if not chunk:
                raise ConnectionResetError("WebSocket frame ended early.")
            chunks.extend(chunk)
        return bytes(chunks)

    def _send_ws(self, payload, send_lock=None):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        header = bytearray([0x81])
        if len(body) < 126:
            header.append(len(body))
        elif len(body) < 65536:
            header.extend([126])
            header.extend(struct.pack("!H", len(body)))
        else:
            header.extend([127])
            header.extend(struct.pack("!Q", len(body)))
        if send_lock is None:
            self.wfile.write(bytes(header) + body)
            self.wfile.flush()
            return
        with send_lock:
            self.wfile.write(bytes(header) + body)
            self.wfile.flush()

    def log_message(self, *args):
        return


def _walk_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def _is_secret_key(key):
    normalized = str(key).lower()
    if normalized.endswith(("_path", "_file", "_url")):
        return False
    return any(
        word in normalized
        for word in ("api_key", "access_token", "refresh_token", "password", "client_secret")
    )


def _registry_items(registry, method_name):
    if registry is None:
        return []
    method = getattr(registry, method_name, None)
    if method is None:
        return []
    items = method()
    return [
        item.to_dict()
        if hasattr(item, "to_dict")
        else asdict(item)
        if is_dataclass(item)
        else getattr(item, "__dict__", str(item))
        for item in items
    ]


def _ability_items(registry, metrics=None):
    if registry is None:
        return []
    result = []
    for ability in registry.list():
        metadata = getattr(ability, "metadata", ability)
        data = asdict(metadata) if is_dataclass(metadata) else dict(getattr(metadata, "__dict__", {}))
        enabled = bool(data.get("enabled", True))
        data.update(
            {
                "id": str(data.get("id", "")),
                "name": str(data.get("name", data.get("id", "Unknown"))),
                "health": "READY" if enabled else "DISABLED",
                "message": "Available for planning." if enabled else "Capability is disabled.",
                "latency_ms": (metrics or {}).get(str(data.get("id", "")), {}).get("latency_ms"),
                "last_call": (metrics or {}).get(str(data.get("id", "")), {}).get("last_call", ""),
            }
        )
        result.append(data)
    return result


def _memory_stats(items):
    counts = {
        "preference": 0,
        "long_term": 0,
        "working": 0,
        "correction": 0,
        "personal_lexicon": 0,
    }
    aliases = {
        "fact": "long_term",
        "goal": "long_term",
        "project": "long_term",
        "routine": "long_term",
        "lexicon": "personal_lexicon",
    }
    for item in items:
        kind = str(item.get("memory_type", item.get("category", "long_term"))).lower()
        kind = aliases.get(kind, kind)
        if kind in counts:
            counts[kind] += 1
    return {"total": len(items), "types": counts}


def _provider_items(backend):
    config = backend.config()
    snapshot = backend.hub.snapshot()
    events = snapshot["events"]
    diagnostics = (
        backend.diagnostics_collector.get_snapshot()
        if backend.diagnostics_collector is not None
        else None
    )
    performance = getattr(diagnostics, "performance", None)
    domains = [
        ("Weather", config.get("weather", {}).get("provider", "not configured")),
        ("Mail", config.get("mail", {}).get("provider", "not configured")),
        ("Calendar", config.get("calendar", {}).get("provider", "not configured")),
        ("Contacts", config.get("contacts", {}).get("provider", "not configured")),
        ("Memory", "json"),
        ("Voice", config.get("tts_provider", config.get("tts", {}).get("provider", "unknown"))),
        ("STT", config.get("stt", {}).get("provider", "unknown")),
        ("TTS", config.get("tts", {}).get("provider", "unknown")),
    ]
    result = []
    for domain, provider in domains:
        matches = [
            event
            for event in events
            if domain.lower() in (
                event["type"] + " " + json.dumps(event["payload"], default=str)
            ).lower()
        ]
        latest = matches[-1] if matches else None
        failed = latest and any(
            word in (latest["type"] + " " + json.dumps(latest["payload"], default=str)).lower()
            for word in ("failed", "error", "expired", "auth_required")
        )
        latency = _event_latency(latest)
        if latency is None and domain == "STT" and performance is not None:
            latency = int(float(getattr(performance, "stt_latency", 0)) * 1000)
        if latency is None and domain == "TTS" and performance is not None:
            latency = int(float(getattr(performance, "tts_latency", 0)) * 1000)
        result.append(
            {
                "domain": domain,
                "provider": str(provider),
                "status": "DEGRADED" if failed else "ONLINE",
                "response_ms": latency,
                "last_call": latest["timestamp"] if latest else "",
                "message": "Check authentication or recent provider error." if failed else "Configured and ready.",
            }
        )
    return result


def _event_latency(event):
    if not event:
        return None
    payload = event.get("payload", {})
    for key in ("latency_ms", "duration_ms", "elapsed_ms"):
        if key in payload:
            try:
                return int(float(payload[key]))
            except (TypeError, ValueError):
                return None
    return None
