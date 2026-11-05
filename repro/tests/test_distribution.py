"""Guard required public workflow support files, not private runtime payloads."""
from pathlib import Path
import re
import unittest


class DistributionTests(unittest.TestCase):
    def test_workflow_base_config_is_published_with_safe_local_execution(self):
        config = Path(__file__).resolve().parents[2] / 'BioLLM_RawDataAnalysis/workflow/nextflow.config'
        self.assertTrue(config.is_file(), 'Published workflow needs its base nextflow.config; compiled runs include it')
        source = config.read_text(encoding='utf-8')
        process = re.search(r'process\s*\{([^{}]*)\}', source)
        self.assertIsNotNone(process, 'Base config must declare its local process execution contract')
        for directive in (r"executor\s*=\s*'local'", r"errorStrategy\s*=\s*'terminate'",
                          r"shell\s*=\s*\['/bin/bash',\s*'-euo',\s*'pipefail'\]"):
            self.assertRegex(process.group(1), directive)
        # Keep the published baseline self-contained, without environment-specific
        # imports, interpolated credentials, private directories or shell commands.
        self.assertNotRegex(source, r'includeConfig|System\.|\$|/home/|/mnt/|[A-Z]:\\|https?://|\.execute\(')


if __name__ == '__main__':
    unittest.main()
