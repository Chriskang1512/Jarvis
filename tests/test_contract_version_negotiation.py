import unittest
from datetime import date

from jarvis.runtime.planner import (
    AgentPlan,
    CapabilityVersionRegistry,
    CapabilityVersionRequirement,
    ContractNegotiationError,
    ContractSupport,
    ContractVersionNegotiator,
    PlanStep,
    VersionAdapter,
    VersionAdapterRegistry,
    normalize_contract_version,
    normalize_sunset_date,
)


class TestContractVersionNegotiation(unittest.TestCase):
    def test_normalizes_v_prefix_and_major_only_versions(self):
        self.assertEqual(normalize_contract_version("v2"), "2.0")
        self.assertEqual(normalize_contract_version("2"), "2.0")
        self.assertEqual(normalize_contract_version("2.1"), "2.1")

    def test_selects_highest_directly_supported_version(self):
        planner = ContractSupport("planner", ("1.0", "2.0"), preferred_version="2.0")
        runtime = ContractSupport("runtime", ("1.0", "2.0"))

        result = ContractVersionNegotiator().negotiate(planner, runtime)

        self.assertTrue(result.direct)
        self.assertEqual(result.selected_version, "2.0")

    def test_resolves_multistep_adapter_path(self):
        registry = VersionAdapterRegistry()
        registry.register(VersionAdapter("v3-to-v2", "3.0", "2.0", lambda value: value + ["v2"]))
        registry.register(VersionAdapter("v2-to-v1", "2.0", "1.0", lambda value: value + ["v1"]))
        planner = ContractSupport("planner", ("3.0",))
        runtime = ContractSupport("runtime", ("1.0",))

        result = ContractVersionNegotiator(registry).negotiate(planner, runtime)
        path = registry.find_path(result.producer_version, (result.selected_version,))

        self.assertEqual(result.adapter_names, ("v3-to-v2", "v2-to-v1"))
        self.assertEqual(registry.adapt([], path), ["v2", "v1"])

    def test_fails_closed_when_no_common_or_adapter_version_exists(self):
        planner = ContractSupport("planner", ("2.0",))
        runtime = ContractSupport("runtime", ("1.0",))

        with self.assertRaises(ContractNegotiationError) as raised:
            ContractVersionNegotiator().negotiate(planner, runtime)

        self.assertEqual(raised.exception.code, "CONTRACT_VERSION_NOT_NEGOTIABLE")

    def test_rejects_duplicate_adapter_edges(self):
        registry = VersionAdapterRegistry()
        registry.register(VersionAdapter("first", "2.0", "1.0", lambda value: value))

        with self.assertRaises(ContractNegotiationError) as raised:
            registry.register(VersionAdapter("second", "v2", "v1", lambda value: value))

        self.assertEqual(raised.exception.code, "VERSION_ADAPTER_ALREADY_REGISTERED")

    def test_blocks_capability_below_minimum_contract(self):
        capabilities = CapabilityVersionRegistry()
        capabilities.register(CapabilityVersionRequirement("calendar.create", "2.0", "3.0"))
        planner = ContractSupport("planner", ("1.0",))
        runtime = ContractSupport("runtime", ("1.0",))

        with self.assertRaises(ContractNegotiationError) as raised:
            ContractVersionNegotiator(capability_registry=capabilities).negotiate(
                planner,
                runtime,
                capabilities=("calendar.create",),
            )

        self.assertEqual(raised.exception.code, "CAPABILITY_CONTRACT_VERSION_UNSUPPORTED")
        self.assertEqual(raised.exception.details[0].capability, "calendar.create")
        self.assertEqual(raised.exception.details[0].required_version, "2.0")

    def test_warns_when_capability_is_below_recommended_contract(self):
        capabilities = CapabilityVersionRegistry()
        capabilities.register(CapabilityVersionRequirement("calendar.create", "2.0", "3.0"))
        planner = ContractSupport("planner", ("2.0",))
        runtime = ContractSupport("runtime", ("2.0",))

        result = ContractVersionNegotiator(capability_registry=capabilities).negotiate(
            planner,
            runtime,
            capabilities=("calendar.create",),
        )

        self.assertEqual(len(result.capability_issues), 1)
        self.assertEqual(
            result.capability_issues[0].code,
            "CAPABILITY_CONTRACT_VERSION_BELOW_RECOMMENDED",
        )
        self.assertEqual(result.capability_issues[0].severity, "warning")

    def test_all_requested_capabilities_are_checked_after_adapter_negotiation(self):
        adapters = VersionAdapterRegistry()
        adapters.register(VersionAdapter("v3-to-v2", "3.0", "2.0", lambda value: value))
        capabilities = CapabilityVersionRegistry()
        capabilities.register(CapabilityVersionRequirement("calendar.create", "2.0"))
        capabilities.register(CapabilityVersionRequirement("mail.send", "3.0"))

        with self.assertRaises(ContractNegotiationError) as raised:
            ContractVersionNegotiator(adapters, capabilities).negotiate(
                ContractSupport("planner", ("3.0",)),
                ContractSupport("runtime", ("2.0",)),
                capabilities=("calendar.create", "mail.send"),
            )

        self.assertEqual(raised.exception.details[0].capability, "mail.send")

    def test_negotiate_plan_extracts_capability_operations(self):
        capabilities = CapabilityVersionRegistry()
        capabilities.register(CapabilityVersionRequirement("calendar.create", "2.0"))
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(PlanStep("step-1", 1, "calendar", "create"),),
            contract_version="1.0",
        )

        with self.assertRaises(ContractNegotiationError) as raised:
            ContractVersionNegotiator(capability_registry=capabilities).negotiate_plan(
                ContractSupport("planner", ("1.0",)),
                ContractSupport("runtime", ("1.0",)),
                plan,
            )

        self.assertEqual(raised.exception.details[0].capability, "calendar.create")

    def test_warns_when_runtime_passes_deprecated_after_version(self):
        capabilities = CapabilityVersionRegistry()
        capabilities.register(
            CapabilityVersionRequirement(
                "calendar.create",
                "2.0",
                recommended="3.0",
                deprecated_after="4.0",
            )
        )

        result = ContractVersionNegotiator(capability_registry=capabilities).negotiate(
            ContractSupport("planner", ("5.0",)),
            ContractSupport("runtime", ("5.0",)),
            capabilities=("calendar.create",),
        )

        self.assertEqual(result.capability_issues[0].code, "CAPABILITY_CONTRACT_DEPRECATED")
        self.assertEqual(result.capability_issues[0].required_version, "4.0")

    def test_future_sunset_returns_scheduled_warning(self):
        capabilities = CapabilityVersionRegistry()
        capabilities.register(CapabilityVersionRequirement("mail.send", "1.0", sunset="2027-01"))

        result = ContractVersionNegotiator(
            capability_registry=capabilities,
            today_provider=lambda: date(2026, 7, 24),
        ).negotiate(
            ContractSupport("planner", ("1.0",)),
            ContractSupport("runtime", ("1.0",)),
            capabilities=("mail.send",),
        )

        self.assertEqual(result.capability_issues[0].code, "CAPABILITY_SUNSET_SCHEDULED")
        self.assertEqual(result.capability_issues[0].required_version, "2027-01-01")

    def test_reached_sunset_blocks_execution(self):
        capabilities = CapabilityVersionRegistry()
        capabilities.register(CapabilityVersionRequirement("mail.send", "1.0", sunset="2027-01-01"))

        with self.assertRaises(ContractNegotiationError) as raised:
            ContractVersionNegotiator(
                capability_registry=capabilities,
                today_provider=lambda: date(2027, 1, 1),
            ).negotiate(
                ContractSupport("planner", ("1.0",)),
                ContractSupport("runtime", ("1.0",)),
                capabilities=("mail.send",),
            )

        self.assertEqual(raised.exception.code, "CAPABILITY_SUNSET_REACHED")

    def test_sunset_normalization_rejects_invalid_dates(self):
        self.assertEqual(normalize_sunset_date("2027-01"), "2027-01-01")
        self.assertEqual(normalize_sunset_date("2027-01-15"), "2027-01-15")
        with self.assertRaises(ContractNegotiationError) as raised:
            normalize_sunset_date("2027-13")
        self.assertEqual(raised.exception.code, "CAPABILITY_SUNSET_INVALID")


if __name__ == "__main__":
    unittest.main()
