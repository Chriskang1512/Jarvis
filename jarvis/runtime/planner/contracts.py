import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4


CONTRACT_VERSION = "1.0"
SUPPORTED_CONTRACT_VERSIONS = (CONTRACT_VERSION,)


@dataclass(frozen=True)
class GoalEnvelope:
    """Versioned user goal accepted by Agent Core."""

    normalized_goal: str
    requested_outcomes: tuple[str, ...] = ()
    constraints: dict = field(default_factory=dict)
    conversation_id: str = ""
    source: str = "runtime"
    raw_text_ref: str = ""
    goal_id: str = ""
    created_at: str = ""
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self):
        object.__setattr__(self, "requested_outcomes", tuple(self.requested_outcomes))
        if not self.goal_id:
            object.__setattr__(self, "goal_id", f"GOAL-{uuid4().hex[:10].upper()}")
        if not self.created_at:
            object.__setattr__(self, "created_at", _now())


@dataclass(frozen=True)
class PlanBinding:
    """Connect one step output to a later step input."""

    source_step_id: str
    source_path: str
    target_step_id: str
    target_path: str
    transform: str = ""
    required: bool = True


@dataclass(frozen=True)
class PlanStep:
    """Provider-neutral capability operation proposed to Agent Core."""

    step_id: str
    ordinal: int
    capability: str
    operation: str
    input: dict = field(default_factory=dict)
    input_schema_version: str = CONTRACT_VERSION
    output_schema_version: str = CONTRACT_VERSION
    depends_on: tuple[str, ...] = ()
    required: bool = True
    side_effect: str = "none"
    permission: str = "safe"
    retry_policy: str = "none"
    verification_policy: str = "none"
    idempotency_policy: str = "none"
    parallel_group: str = ""
    execution_target: str = ""

    def __post_init__(self):
        object.__setattr__(self, "depends_on", tuple(self.depends_on))


@dataclass(frozen=True)
class AgentPlan:
    """Immutable, versioned plan validated by Agent Core."""

    goal_id: str
    steps: tuple[PlanStep, ...] = ()
    bindings: tuple[PlanBinding, ...] = ()
    required_permissions: tuple[str, ...] = ()
    status: str = "proposed"
    plan_id: str = ""
    plan_version: int = 1
    planner_version: str = CONTRACT_VERSION
    created_at: str = ""
    optimized_from_version: int | None = None
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self):
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(self, "bindings", tuple(self.bindings))
        object.__setattr__(self, "required_permissions", tuple(self.required_permissions))
        if not self.plan_id:
            object.__setattr__(self, "plan_id", f"PLAN-{uuid4().hex[:10].upper()}")
        if not self.created_at:
            object.__setattr__(self, "created_at", _now())

    def semantic_fingerprint(self):
        """Hash user-visible outcomes, permissions, and side effects."""
        payload = {
            "goal_id": self.goal_id,
            "steps": [
                {
                    "capability": step.capability,
                    "operation": step.operation,
                    "input": step.input,
                    "required": step.required,
                    "side_effect": step.side_effect,
                    "permission": step.permission,
                    "verification_policy": step.verification_policy,
                    "idempotency_policy": step.idempotency_policy,
                    "depends_on": sorted(step.depends_on),
                }
                for step in sorted(self.steps, key=lambda item: item.step_id)
            ],
            "bindings": [
                {
                    "source_step_id": binding.source_step_id,
                    "source_path": binding.source_path,
                    "target_step_id": binding.target_step_id,
                    "target_path": binding.target_path,
                    "transform": binding.transform,
                    "required": binding.required,
                }
                for binding in sorted(
                    self.bindings,
                    key=lambda item: (
                        item.source_step_id,
                        item.source_path,
                        item.target_step_id,
                        item.target_path,
                    ),
                )
            ],
            "required_permissions": sorted(self.required_permissions),
        }
        encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _now():
    return datetime.now().isoformat(timespec="seconds")


def agent_plan_to_dict(plan, redact_inputs=False):
    """Serialize an AgentPlan for journal replay."""
    return {
        "goal_id": plan.goal_id,
        "steps": [
            {
                "step_id": step.step_id,
                "ordinal": step.ordinal,
                "capability": step.capability,
                "operation": step.operation,
                "input": (
                    _redact_replay_value(dict(step.input))
                    if redact_inputs
                    else dict(step.input)
                ),
                "input_schema_version": step.input_schema_version,
                "output_schema_version": step.output_schema_version,
                "depends_on": list(step.depends_on),
                "required": step.required,
                "side_effect": step.side_effect,
                "permission": step.permission,
                "retry_policy": step.retry_policy,
                "verification_policy": step.verification_policy,
                "idempotency_policy": step.idempotency_policy,
                "parallel_group": step.parallel_group,
                "execution_target": step.execution_target,
            }
            for step in plan.steps
        ],
        "bindings": [
            {
                "source_step_id": binding.source_step_id,
                "source_path": binding.source_path,
                "target_step_id": binding.target_step_id,
                "target_path": binding.target_path,
                "transform": binding.transform,
                "required": binding.required,
            }
            for binding in plan.bindings
        ],
        "required_permissions": list(plan.required_permissions),
        "status": plan.status,
        "plan_id": plan.plan_id,
        "plan_version": plan.plan_version,
        "planner_version": plan.planner_version,
        "created_at": plan.created_at,
        "optimized_from_version": plan.optimized_from_version,
        "contract_version": plan.contract_version,
    }


def agent_plan_from_dict(data):
    """Restore an AgentPlan from a privacy-controlled journal snapshot."""
    return AgentPlan(
        goal_id=data["goal_id"],
        steps=tuple(PlanStep(**step) for step in data.get("steps", [])),
        bindings=tuple(PlanBinding(**binding) for binding in data.get("bindings", [])),
        required_permissions=tuple(data.get("required_permissions", [])),
        status=data.get("status", "proposed"),
        plan_id=data.get("plan_id", ""),
        plan_version=int(data.get("plan_version", 1)),
        planner_version=data.get("planner_version", CONTRACT_VERSION),
        created_at=data.get("created_at", ""),
        optimized_from_version=data.get("optimized_from_version"),
        contract_version=data.get("contract_version", CONTRACT_VERSION),
    )


def _redact_replay_value(value):
    """Preserve validation-relevant shape without retaining sensitive values."""
    if isinstance(value, dict):
        return {str(key): _redact_replay_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_replay_value(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_replay_value(item) for item in value]
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return 0
    if isinstance(value, float):
        return 0.0
    if isinstance(value, str):
        return "<redacted>"
    return None
