"""Project skill allowlist: config block, json record, validation exit codes."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPT = SKILL_DIR / 'scripts' / 'skill_scope.py'


def load():
    spec = importlib.util.spec_from_file_location('skill_scope_under_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SkillScopeTests(unittest.TestCase):
    def setUp(self):
        self.module = load()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.skill = None
        for name in ('design-patterns', 'test-driven-development'):
            if (Path(os.path.expanduser('~')) / '.codex' / 'skills' / name / 'SKILL.md').exists():
                self.skill = name
                break

    def tearDown(self):
        self.tmp.cleanup()

    def test_preview_writes_nothing(self):
        if not self.skill:
            self.skipTest('no installed skill on this machine')
        self.assertEqual(self.module.main(['--project', str(self.root), '--skills', self.skill]), 0)
        self.assertFalse((self.root / '.codex' / 'config.toml').exists())

    def test_write_creates_config_and_allowlist(self):
        if not self.skill:
            self.skipTest('no installed skill on this machine')
        self.assertEqual(self.module.main(['--project', str(self.root), '--skills', self.skill, '--write']), 0)
        cfg = (self.root / '.codex' / 'config.toml').read_text(encoding='utf-8')
        self.assertIn('include_instructions = false', cfg)
        data = json.loads((self.root / 'Docs' / 'ai' / 'skill-scope.json').read_text(encoding='utf-8'))
        self.assertEqual([s['name'] for s in data['skills']], [self.skill])
        self.assertIn(data['skills'][0]['scope'], ('global', 'project'))
        self.assertIn('role skill sets are global', data['note'].lower())

    def test_project_skill_wins(self):
        local = self.root / '.codex' / 'skills' / 'local-demo'
        local.mkdir(parents=True)
        (local / 'SKILL.md').write_text('---\nname: local-demo\n---\n', encoding='utf-8')
        self.assertEqual(self.module.main(['--project', str(self.root), '--skills', 'local-demo', '--write']), 0)
        data = json.loads((self.root / 'Docs' / 'ai' / 'skill-scope.json').read_text(encoding='utf-8'))
        self.assertEqual(data['skills'][0]['scope'], 'project')

    def test_unknown_skill_exits_one(self):
        self.assertEqual(self.module.main(['--project', str(self.root), '--skills', 'no-such-skill-xyz']), 1)

    def test_check_accepts_written_project(self):
        if not self.skill:
            self.skipTest('no installed skill on this machine')
        self.module.main(['--project', str(self.root), '--skills', self.skill, '--write'])
        self.assertEqual(self.module.main(['--project', str(self.root), '--check']), 0)

    def test_missing_skills_exits_two(self):
        self.assertEqual(self.module.main(['--project', str(self.root)]), 2)


if __name__ == '__main__':
    import argparse
    _ap = argparse.ArgumentParser(add_help=False)
    _ap.add_argument('--skill')
    _, _rest = _ap.parse_known_args()
    unittest.main(argv=[sys.argv[0]] + _rest)
