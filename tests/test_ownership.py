import subprocess
import sys
import unittest
import uuid

from instrumentio.ownership import InstrumentLease


class OwnershipTests(unittest.TestCase):
    def test_other_process_is_excluded_until_shutdown_releases_ownership(self):
        address = "fake-" + uuid.uuid4().hex
        lease = InstrumentLease(address)
        self.addCleanup(lease.close)
        script = "from instrumentio.ownership import InstrumentLease; import sys; InstrumentLease(sys.argv[1]).close()"
        blocked = subprocess.run([sys.executable, "-c", script, address.upper()], capture_output=True, text=True)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("already in use", blocked.stderr)
        lease.close()
        allowed = subprocess.run([sys.executable, "-c", script, address], capture_output=True, text=True)
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
