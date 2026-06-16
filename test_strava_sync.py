import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT = os.path.dirname(__file__)
RUN_PAGE = os.path.join(ROOT, "run_page")
STRAVA_SYNC_FILE = os.path.join(RUN_PAGE, "strava_sync.py")


class FakeGenerator:
    def __init__(self, db_path):
        self.db_path = db_path
        self.session = object()
        self.events = []

    def set_strava_config(self, client_id, client_secret, refresh_token):
        self.events.append("config")

    def sync(self, force):
        self.events.append("sync")

    def load(self):
        self.events.append("load")
        return [{"run_id": 1, "location_country": "Chengdu, Sichuan, China"}]


def load_strava_sync_module():
    spec = importlib.util.spec_from_file_location(
        "strava_sync_under_test", STRAVA_SYNC_FILE
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["strava_sync_under_test"] = module
    spec.loader.exec_module(module)
    return module


class StravaSyncTest(unittest.TestCase):
    def test_fixes_locations_before_exporting_activities_json(self):
        config_module = types.ModuleType("config")
        config_module.JSON_FILE = "unused.json"
        config_module.SQL_FILE = "unused.db"

        generator_module = types.ModuleType("generator")
        generator_module.Generator = FakeGenerator

        fix_location_module = types.ModuleType("fix_location")
        fix_location_module.fix_locations = lambda session: None

        generator = FakeGenerator("data.db")
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            json_path = tmp.name
        self.addCleanup(lambda: os.path.exists(json_path) and os.remove(json_path))

        with patch.dict(
            sys.modules,
            {
                "config": config_module,
                "generator": generator_module,
                "fix_location": fix_location_module,
            },
        ):
            strava_sync = load_strava_sync_module()

        with (
            patch.object(strava_sync, "Generator", return_value=generator),
            patch.object(strava_sync, "SQL_FILE", "data.db"),
            patch.object(strava_sync, "JSON_FILE", json_path),
            patch.object(strava_sync, "fix_locations", create=True) as fix_locations,
        ):
            fix_locations.side_effect = lambda session: generator.events.append("fix")

            strava_sync.run_strava_sync("client", "secret", "refresh")

        self.assertEqual(generator.events, ["config", "sync", "fix", "load"])
        fix_locations.assert_called_once_with(generator.session)
        with open(json_path) as fh:
            self.assertEqual(
                json.load(fh),
                [{"run_id": 1, "location_country": "Chengdu, Sichuan, China"}],
            )


if __name__ == "__main__":
    unittest.main()
