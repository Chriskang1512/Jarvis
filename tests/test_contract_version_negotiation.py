import unittest

from jarvis.runtime.planner import (
    ContractNegotiationError,
    ContractSupport,
    ContractVersionNegotiator,
    VersionAdapter,
    VersionAdapterRegistry,
    normalize_contract_version,
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


if __name__ == "__main__":
    unittest.main()
