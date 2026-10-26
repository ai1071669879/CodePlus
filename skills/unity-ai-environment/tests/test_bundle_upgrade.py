"""Initialization and integration-contract acceptance for both distributions."""
import unittest
from upgrade_support import Harness


class BundleUpgradeTests(Harness):
    def capability(self, **changes):
        integration = {'enabled': False, 'provider': 'example', 'group': '',
                       'origin': 'https://example.com/tool', 'version': '', 'license': '',
                       'transport': 'command', 'endpoint': '', 'network': [],
                       'environment_variables': [], 'probe': [], 'version_pattern': '',
                       'required': False, 'timeout_seconds': 5, 'writes': False}
        integration.update(changes)
        return {'state': 'unconfigured', 'command': [], 'integration': integration}

    def profile_with(self, capabilities):
        self.initialize()
        profile = self.read_json('Docs/ai/project-profile.json')
        profile['capabilities'].update(capabilities)
        self.write_json('Docs/ai/project-profile.json', profile)

    def test_bundle_contains_executable_helpers_and_single_source_templates(self):
        self.initialize()
        for relative in ['tools/ai/environment.py', 'tools/ai/quality.py', 'tools/ai/evaluate.py',
                         'Docs/ai/tool-integrations.md', 'Docs/ai/quality-workflows.md',
                         'Docs/ai/architecture-policy.json', 'Docs/ai/evals.json', 'Docs/ai/gitleaks.toml']:
            self.assertTrue((self.root / relative).is_file(), relative)
        profile = self.read_json('Docs/ai/project-profile.json')
        for name in ['secret-scan', 'semantic-navigation', 'library-docs', 'spec-delta']:
            self.assertFalse(profile['capabilities'][name]['integration']['enabled'])
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unknown_integration_field_is_not_silently_accepted(self):
        self.profile_with({'example': self.capability(enabeld=True)})
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_only_one_editor_provider_can_be_enabled(self):
        self.profile_with({'one': self.capability(enabled=True, group='editor'),
                           'two': self.capability(enabled=True, group='editor')})
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_remote_endpoint_cannot_embed_credentials_or_use_plain_http(self):
        self.profile_with({'example': self.capability(transport='http', endpoint='http://remote.example.com/mcp')})
        for endpoint in ['http://remote.example.com/mcp', 'https://user:secret@example.com/mcp',
                         'https://example.com/mcp?token=value']:
            profile = self.read_json('Docs/ai/project-profile.json')
            profile['capabilities']['example']['integration']['endpoint'] = endpoint
            self.write_json('Docs/ai/project-profile.json', profile)
            result, data = self.installed('check')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_loopback_endpoint_and_environment_names_are_valid_metadata(self):
        self.profile_with({'example': self.capability(transport='http', endpoint='http://127.0.0.1:8123/mcp',
                                                       environment_variables=['TOOL_API_KEY'])})
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        profile = self.read_json('Docs/ai/project-profile.json')
        profile['capabilities']['example']['integration']['environment_variables'] = ['TOOL_API_KEY=value']
        self.write_json('Docs/ai/project-profile.json', profile)
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
