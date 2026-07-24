import json
from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class OptimizationRecord:
    optimizer_version: str
    input_plan_version: int
    output_plan_version: int
    rules_applied: tuple[str, ...]
    semantic_fingerprint_before: str
    semantic_fingerprint_after: str
    journal_entries: tuple[object, ...] = ()
    invariants_verified: bool = True

    def to_dict(self):
        return {
            "optimizer_version": self.optimizer_version,
            "input_plan_version": self.input_plan_version,
            "output_plan_version": self.output_plan_version,
            "rules_applied": list(self.rules_applied),
            "semantic_fingerprint_before": self.semantic_fingerprint_before,
            "semantic_fingerprint_after": self.semantic_fingerprint_after,
            "journal_entries": [entry.to_dict() for entry in self.journal_entries],
            "invariants_verified": self.invariants_verified,
        }


@dataclass(frozen=True)
class OptimizationJournalEntry:
    rule_id: str
    reason: str
    before_step_ids: tuple[str, ...]
    after_step_ids: tuple[str, ...]
    details: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "rule_id": self.rule_id,
            "reason": self.reason,
            "before_step_ids": list(self.before_step_ids),
            "after_step_ids": list(self.after_step_ids),
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class OptimizationResult:
    plan: object
    record: OptimizationRecord


class NoOpPlanOptimizer:
    """Auditable optimizer boundary that preserves plan semantics."""

    version = "1.0-noop"

    def optimize(self, plan):
        before = plan.semantic_fingerprint()
        optimized = replace(
            plan,
            status="optimized",
            plan_version=plan.plan_version + 1,
            optimized_from_version=plan.plan_version,
        )
        after = optimized.semantic_fingerprint()
        if before != after:
            raise ValueError("OPTIMIZER_SEMANTIC_CHANGE")
        return OptimizationResult(
            plan=optimized,
            record=OptimizationRecord(
                optimizer_version=self.version,
                input_plan_version=plan.plan_version,
                output_plan_version=optimized.plan_version,
                rules_applied=(),
                semantic_fingerprint_before=before,
                semantic_fingerprint_after=after,
            ),
        )


class SmartPlanOptimizer:
    """Apply conservative, auditable plan optimizations."""

    version = "2.0-smart"

    def __init__(self, ability_registry):
        self.ability_registry = ability_registry

    def optimize(self, plan):
        before = plan.semantic_fingerprint()
        working = plan
        entries = []
        working, entry = self._remove_duplicates(working)
        if entry:
            entries.append(entry)
        working, entry = self._remove_dead_steps(working)
        if entry:
            entries.append(entry)
        working, entry = self._reorder_dependencies(working)
        if entry:
            entries.append(entry)
        working, entry = self._mark_parallel_reads(working)
        if entry:
            entries.append(entry)
        optimized = replace(
            working,
            status="optimized",
            plan_version=plan.plan_version + 1,
            optimized_from_version=plan.plan_version,
        )
        _assert_optimizer_invariants(plan, optimized)
        after = optimized.semantic_fingerprint()
        return OptimizationResult(
            plan=optimized,
            record=OptimizationRecord(
                optimizer_version=self.version,
                input_plan_version=plan.plan_version,
                output_plan_version=optimized.plan_version,
                rules_applied=tuple(entry.rule_id for entry in entries),
                semantic_fingerprint_before=before,
                semantic_fingerprint_after=after,
                journal_entries=tuple(entries),
                invariants_verified=True,
            ),
        )

    def _remove_duplicates(self, plan):
        target_ids = {binding.target_step_id for binding in plan.bindings}
        seen = {}
        replacement = {}
        kept = []
        removed = []
        for step in plan.steps:
            operation = self.ability_registry.get_operation(step.capability, step.operation)
            if operation is None or not operation.deduplicatable or step.step_id in target_ids:
                kept.append(step)
                continue
            signature = _step_signature(step)
            if signature not in seen:
                seen[signature] = step.step_id
                kept.append(step)
                continue
            replacement[step.step_id] = seen[signature]
            removed.append(step.step_id)
        if not removed:
            return plan, None
        rewritten = _rewrite_plan(plan, kept, replacement)
        return rewritten, OptimizationJournalEntry(
            "OPT-001",
            "Duplicate safe operation removed",
            tuple(step.step_id for step in plan.steps),
            tuple(step.step_id for step in rewritten.steps),
            {"removed_step_ids": removed, "replacement": replacement},
        )

    def _remove_dead_steps(self, plan):
        referenced = {dependency for step in plan.steps for dependency in step.depends_on}
        referenced.update(binding.source_step_id for binding in plan.bindings)
        removed = []
        kept = []
        for step in plan.steps:
            operation = self.ability_registry.get_operation(step.capability, step.operation)
            dead = (
                not step.required
                and step.input.get("_dead_step") is True
                and step.step_id not in referenced
                and operation is not None
                and operation.side_effect == "none"
            )
            if dead:
                removed.append(step.step_id)
            else:
                kept.append(step)
        if not removed:
            return plan, None
        rewritten = replace(plan, steps=tuple(kept))
        return rewritten, OptimizationJournalEntry(
            "OPT-004",
            "Unreferenced optional dead step removed",
            tuple(step.step_id for step in plan.steps),
            tuple(step.step_id for step in rewritten.steps),
            {"removed_step_ids": removed},
        )

    def _reorder_dependencies(self, plan):
        ordered = _topological_steps(plan.steps)
        if tuple(step.step_id for step in ordered) == tuple(step.step_id for step in plan.steps):
            return plan, None
        ordered = tuple(replace(step, ordinal=index) for index, step in enumerate(ordered, start=1))
        rewritten = replace(plan, steps=ordered)
        return rewritten, OptimizationJournalEntry(
            "OPT-002",
            "Dependency topological order restored",
            tuple(step.step_id for step in plan.steps),
            tuple(step.step_id for step in rewritten.steps),
        )

    def _mark_parallel_reads(self, plan):
        groups = {}
        for step in plan.steps:
            operation = self.ability_registry.get_operation(step.capability, step.operation)
            if operation is not None and operation.parallel_safe and step.side_effect == "none":
                groups.setdefault(tuple(sorted(step.depends_on)), []).append(step.step_id)
        parallel_groups = [ids for ids in groups.values() if len(ids) > 1]
        if not parallel_groups:
            return plan, None
        mapping = {}
        for index, ids in enumerate(parallel_groups, start=1):
            for step_id in ids:
                mapping[step_id] = f"PG-{index}"
        steps = tuple(replace(step, parallel_group=mapping.get(step.step_id, step.parallel_group)) for step in plan.steps)
        rewritten = replace(plan, steps=steps)
        return rewritten, OptimizationJournalEntry(
            "OPT-003",
            "Independent safe operations marked parallel",
            tuple(step.step_id for step in plan.steps),
            tuple(step.step_id for step in rewritten.steps),
            {"parallel_groups": mapping},
        )


def _step_signature(step):
    payload = {
        "capability": step.capability,
        "operation": step.operation,
        "input": step.input,
        "depends_on": sorted(step.depends_on),
        "permission": step.permission,
        "side_effect": step.side_effect,
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str)


def _rewrite_plan(plan, kept_steps, replacement):
    steps = tuple(
        replace(
            step,
            depends_on=tuple(dict.fromkeys(replacement.get(item, item) for item in step.depends_on)),
        )
        for step in kept_steps
    )
    bindings = tuple(
        replace(
            binding,
            source_step_id=replacement.get(binding.source_step_id, binding.source_step_id),
            target_step_id=replacement.get(binding.target_step_id, binding.target_step_id),
        )
        for binding in plan.bindings
        if binding.target_step_id not in replacement
    )
    return replace(plan, steps=steps, bindings=bindings)


def _topological_steps(steps):
    by_id = {step.step_id: step for step in steps}
    pending = {step.step_id: set(item for item in step.depends_on if item in by_id) for step in steps}
    ordered = []
    while pending:
        ready = sorted(
            (step_id for step_id, dependencies in pending.items() if not dependencies),
            key=lambda step_id: (by_id[step_id].ordinal, step_id),
        )
        if not ready:
            return tuple(steps)
        for step_id in ready:
            ordered.append(by_id[step_id])
            pending.pop(step_id)
            for dependencies in pending.values():
                dependencies.discard(step_id)
    return tuple(ordered)


def _assert_optimizer_invariants(before, after):
    if before.goal_id != after.goal_id:
        raise ValueError("OPTIMIZER_GOAL_CHANGED")
    if tuple(sorted(before.required_permissions)) != tuple(sorted(after.required_permissions)):
        raise ValueError("OPTIMIZER_PERMISSION_CHANGED")
    before_effects = sorted(_side_effect_signature(step) for step in before.steps if step.side_effect != "none")
    after_effects = sorted(_side_effect_signature(step) for step in after.steps if step.side_effect != "none")
    if before_effects != after_effects:
        raise ValueError("OPTIMIZER_SIDE_EFFECT_CHANGED")


def _side_effect_signature(step):
    payload = {
        "capability": step.capability,
        "operation": step.operation,
        "input": step.input,
        "permission": step.permission,
        "side_effect": step.side_effect,
        "required": step.required,
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str)
