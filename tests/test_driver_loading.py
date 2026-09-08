import subprocess
import sys
import unittest
from unittest.mock import patch

from instrumentio import bindings


class DriverLoadingTests(unittest.TestCase):
    def test_remote_import_does_not_load_drivers(self):
        subprocess.run([sys.executable, "-c", """
import sys
import instrumentio.bridge
assert 'instrumentio.sessions' not in sys.modules
assert 'instrumentio.bindings' not in sys.modules
"""], check=True)

    def test_loader_error_preserves_path_and_cause(self):
        failure = OSError(193, "Wrong architecture")
        with patch.object(bindings.platform, "system", return_value="Windows"), \
             patch.object(bindings.ct, "WinDLL", create=True, side_effect=failure), \
             patch.dict(bindings._load_errors, clear=True):
            library = bindings._load_dll("TEST_INSTRUMENT_DLL", "missing.dll")
            with self.assertRaisesRegex(RuntimeError, "missing.dll.*Wrong architecture") as caught:
                bindings.require_dll(library, "TEST_INSTRUMENT_DLL")
            self.assertIs(caught.exception.__cause__, failure)
