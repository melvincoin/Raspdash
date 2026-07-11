from __future__ import annotations

import importlib
import unittest
from unittest.mock import patch


class ProviderLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app_module = importlib.import_module("raspdash.app")
        self.app_module._provider = None
        self.app_module._provider_name = ""

    def tearDown(self) -> None:
        self.app_module._provider = None
        self.app_module._provider_name = ""

    def test_reuses_provider_without_reloading_config_for_every_sample(self) -> None:
        provider = object()
        config = {"obd": {"provider": "simulated", "simulated": {}}}

        with (
            patch.object(self.app_module, "load_config", return_value=config) as load_config,
            patch.object(self.app_module, "create_provider", return_value=provider) as create_provider,
        ):
            results = [self.app_module.get_provider() for _ in range(100)]

        self.assertTrue(all(result is provider for result in results))
        load_config.assert_called_once_with()
        create_provider.assert_called_once_with("simulated", {})


if __name__ == "__main__":
    unittest.main()
