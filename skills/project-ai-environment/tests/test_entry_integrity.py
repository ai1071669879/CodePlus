"""Root core integrity is required independently of size and manifest ownership."""
import hashlib
import shutil
import unittest

import test_environment as common
import test_core_bootstrap as core
from upgrade_support import Harness


class EntryIntegrityTests(unittest.TestCase):
    setUp = core.EntryBudgetTests.setUp

    def test_short_uncertified_entry_remains_budget_only_unless_core_is_required(self):
        text = 'Read project docs.\n'
        budget = core.BUDGET.check_entry(text, self.certificate)
        self.assertTrue(budget['ok'])
        self.assertFalse(budget['core_matches'])
        strict = core.BUDGET.check_entry(text, self.certificate, require_core=True)
        self.assertFalse(strict['ok'])
        self.assertFalse(strict['core_matches'])
        self.assertTrue(strict['errors'])

    def test_matching_core_preserves_manual_text_and_enforces_complete_budget(self):
        for prefix, expected in (('', True), ('Human rule.\n', True), ('a' * 127, False)):
            with self.subTest(prefix=prefix):
                result = core.BUDGET.check_entry(prefix + self.block, self.certificate, require_core=True)
                self.assertTrue(result['core_matches'])
                self.assertEqual(result['ok'], expected)
        self.assertEqual(
            core.BUDGET.check_entry(self.block, self.certificate, require_core=True)['token_counts'],
            self.certificate['token_counts'])

    def test_missing_duplicate_mutated_and_unterminated_cores_are_rejected(self):
        variants = (
            '', self.block.replace('Read', 'Skip'), self.block * 2,
            self.block.replace('<!-- ai-environment:start -->\n', ''),
            self.block.replace('<!-- ai-environment:end -->\n', ''),
            self.block.rstrip('\n'),
        )
        for text in variants:
            with self.subTest(text=text):
                self.assertLess(len(text.encode('utf-8')), 500)
                result = core.BUDGET.check_entry(text, self.certificate, require_core=True)
                self.assertFalse(result['ok'])
                self.assertFalse(result['core_matches'])
                self.assertTrue(result['errors'])

    def test_malformed_and_overbudget_certificates_cannot_certify_a_short_core(self):
        variants = (
            None,
            dict(self.certificate, schema_version=True),
            dict(self.certificate, template_sha256='0' * 64),
            dict(self.certificate, token_counts={'cl100k_base': -1, 'o200k_base': 1}),
            dict(self.certificate, token_counts={'cl100k_base': 501, 'o200k_base': 1}),
        )
        for certificate in variants:
            with self.subTest(certificate=certificate):
                result = core.BUDGET.check_entry(self.block, certificate, require_core=True)
                self.assertFalse(result['ok'])
                self.assertFalse(result['core_matches'])
                self.assertTrue(result['errors'])


class InstalledEntryIntegrityTests(Harness):
    def test_root_core_corruption_is_rejected_even_with_refreshed_manifest(self):
        self.initialize()
        path = self.root / 'AGENTS.md'
        original = path.read_text(encoding='utf-8')
        short = '<!-- ai-environment:start -->\nRead project docs.\n<!-- ai-environment:end -->\n'
        variants = ('', short, short * 2, original.replace('<!-- ai-environment:start -->', ''))
        for text in variants:
            with self.subTest(text=text):
                path.write_text(text, encoding='utf-8')
                manifest = self.read_json('.ai-environment.json')
                manifest['files']['AGENTS.md'] = hashlib.sha256(path.read_bytes()).hexdigest()
                self.write_json('.ai-environment.json', manifest)
                result, data = self.installed('check')
                self.assertFalse(data['entry_budgets']['AGENTS.md']['ok'])
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertFalse(data['entry_budgets']['AGENTS.md']['core_matches'])
                self.assertTrue(data['entry_budgets']['AGENTS.md']['errors'])

    def test_certified_root_preserves_admissible_human_prefix(self):
        original = '# Human rules\nKeep this.\n'
        (self.root / 'AGENTS.md').write_text(original, encoding='utf-8')
        data = self.initialize()
        self.assertTrue((self.root / 'AGENTS.md').read_text(encoding='utf-8').startswith(original))
        self.assertTrue(data['entry_budgets']['AGENTS.md']['core_matches'])
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(data['entry_budgets']['AGENTS.md']['core_matches'])

    def test_corrupted_short_root_asset_aborts_fresh_install_without_writes(self):
        package = self.case_dir / 'package'
        for relative in ('scripts', 'assets'):
            shutil.copytree(common.SKILL / relative, package / relative)
        (package / 'assets/project/AGENTS.md').write_text('Read project docs.\n', encoding='utf-8')
        before = common.snapshot(self.root)
        result, data = self.command(
            package / 'scripts/bootstrap.py', 'apply', '--project', self.root)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('AGENTS.md', data['conflicts'])
        self.assertFalse(data['entry_budgets']['AGENTS.md']['core_matches'])
        self.assertEqual(common.snapshot(self.root), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
