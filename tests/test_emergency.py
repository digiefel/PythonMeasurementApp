import ctypes as ct
import unittest
from unittest.mock import Mock, patch

from instrumentio import emergency


class EmergencyTests(unittest.TestCase):
    def setUp(self):
        self.visa = Mock()
        for name in ("viOpenDefaultRM", "viOpen", "viSetAttribute", "viClear", "viClose"):
            getattr(self.visa, name).return_value = 0
        self.commands = []
        def write(session, data, length, count):
            self.commands.append(data)
            ct.cast(count, ct.POINTER(ct.c_uint32))[0] = length
            return 0
        def read(session, buffer, length, count):
            buffer.value = b"1\n"
            ct.cast(count, ct.POINTER(ct.c_uint32))[0] = 2
            return 0
        self.visa.viWrite.side_effect = write
        self.visa.viRead.side_effect = read
        patcher = patch.object(emergency, "_load_visa", return_value=self.visa)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_clear_reset_and_completion_are_checked(self):
        emergency.shutdown("fake")
        self.visa.viClear.assert_called_once()
        self.assertEqual(self.commands, [b"*RST\n", b"*OPC?\n"])
        self.assertEqual(self.visa.viClose.call_count, 2)

    def test_failed_clear_still_attempts_reset_and_reports_failure(self):
        self.visa.viClear.return_value = -1073807339
        with self.assertRaises(ExceptionGroup):
            emergency.shutdown("fake")
        self.assertIn(b"*RST\n", self.commands)

    def test_failed_or_partial_write_never_reports_success(self):
        for result in (-1073807339, 0):
            with self.subTest(result=result):
                self.visa.viWrite.side_effect = None
                self.visa.viWrite.return_value = result
                with self.assertRaises(ExceptionGroup):
                    emergency.shutdown("fake")

    def test_failed_completion_never_reports_success(self):
        self.visa.viRead.side_effect = None
        self.visa.viRead.return_value = -1073807339
        with self.assertRaises(ExceptionGroup):
            emergency.shutdown("fake")

    def test_mainframe_failure_does_not_skip_wgfmu_reset(self):
        from instrumentio import bindings
        self.visa.viClear.return_value = -1
        driver = Mock()
        for name in ("WGFMU_openSession", "WGFMU_setTimeout", "WGFMU_initialize", "WGFMU_closeSession"):
            getattr(driver, name).return_value = 0
        with patch.object(bindings, "dll_wgfmu", driver):
            with self.assertRaises(ExceptionGroup):
                emergency.shutdown("fake", wgfmu=True)
        driver.WGFMU_initialize.assert_called_once()
        driver.WGFMU_closeSession.assert_called_once()

    def test_wgfmu_failure_is_not_silently_ignored(self):
        from instrumentio import bindings
        driver = Mock()
        driver.WGFMU_openSession.return_value = 0
        driver.WGFMU_setTimeout.return_value = 0
        driver.WGFMU_initialize.return_value = -1
        driver.WGFMU_closeSession.return_value = 0
        with patch.object(bindings, "dll_wgfmu", driver):
            with self.assertRaises(ExceptionGroup):
                emergency.shutdown("fake", wgfmu=True)
        driver.WGFMU_closeSession.assert_called_once()
