"""Shared black-box fixtures, reusing the original environment harness."""
import json
import unittest
import test_environment as common


class Harness(unittest.TestCase):
    setUp = common.EnvironmentTests.setUp
    cleanup_case = common.EnvironmentTests.cleanup_case
    command = common.EnvironmentTests.command
    bootstrap = common.EnvironmentTests.bootstrap
    installed = common.EnvironmentTests.installed
    initialize = common.EnvironmentTests.initialize
    register = common.EnvironmentTests.register

    def read_json(self, relative):
        return json.loads((self.root / relative).read_text(encoding='utf-8'))

    def write_json(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

    def tool(self, name, *args):
        return self.command(self.root / 'tools/ai' / name, *args, '--project', self.root)
