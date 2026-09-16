import ctypes as ct
import unittest
from unittest.mock import Mock, patch

from instrumentio import sessions


class SessionTests(unittest.TestCase):
    def test_measurement_native_timeout_is_unbounded_then_restored(self):
        session = sessions.B1500Session.__new__(sessions.B1500Session)
        session.session = 1
        session._stream_error_detect = True
        session._stream_eod = False
        def read_timeout(handle, attribute, value):
            ct.cast(value, ct.POINTER(ct.c_uint32))[0] = 10000
            return 0
        for failed in (False, True):
            with self.subTest(failed=failed), patch.object(sessions, "dll_visa32") as visa, patch.object(sessions, "dll_b1500") as driver:
                visa.viGetAttribute.side_effect = read_timeout
                visa.viSetAttribute.return_value = 0
                def measure(*args):
                    self.assertEqual(visa.viSetAttribute.call_args.args[-1], sessions.VI_TMO_INFINITE)
                    if failed:
                        raise RuntimeError("Measurement failed")
                    return 0
                driver.agb1500_readData.side_effect = measure
                if failed:
                    with self.assertRaisesRegex(RuntimeError, "Measurement failed"):
                        session.read_data()
                else:
                    session.read_data()
                self.assertEqual(visa.viSetAttribute.call_args.args[-1], 10000)

    def test_wgfmu_cleanup_resets_disconnects_and_closes_even_after_failure(self):
        session = sessions.WGFMUSession.__new__(sessions.WGFMUSession)
        session._connected_channels = {101, 102}
        with patch.object(sessions, "dll_wgfmu") as driver:
            driver.WGFMU_initialize.return_value = -1
            driver.WGFMU_getErrorSummarySize.return_value = -1
            driver.WGFMU_disconnect.return_value = 0
            driver.WGFMU_closeSession.return_value = 0
            with self.assertRaises(ExceptionGroup):
                session.close()
            self.assertEqual([c.args[0] for c in driver.WGFMU_disconnect.call_args_list], [101, 102])
            driver.WGFMU_closeSession.assert_called_once()
            self.assertEqual(session._connected_channels, set())

    def test_shutdown_attempts_every_step_and_reports_all_errors(self):
        session = sessions.B1500Session.__new__(sessions.B1500Session)
        session._closed = False
        session.session = 1
        session._wgfmu = Mock()
        session._wgfmu.close.side_effect = RuntimeError("WGFMU close failed")
        session.abort_measure = Mock(side_effect=RuntimeError("Abort failed"))
        session.zero_output = Mock()
        session.set_switch = Mock()
        session._check_ret = Mock()
        with patch.object(sessions, "dll_b1500") as driver, \
             patch.object(sessions, "dll_visa32"), \
             patch.object(sessions, "clear_and_confirm", side_effect=RuntimeError("Clear failed")) as clear:
            with self.assertRaises(ExceptionGroup) as caught:
                session.close()
            self.assertEqual(len(caught.exception.exceptions), 2)
            clear.assert_called_once()
            session.abort_measure.assert_not_called()
            session.zero_output.assert_not_called()
            session.set_switch.assert_not_called()
            driver.agb1500_close.assert_called_once_with(1)
            session.close()
            driver.agb1500_close.assert_called_once()

    def test_wgfmu_abort_timeout_is_an_error(self):
        session = sessions.WGFMUSession.__new__(sessions.WGFMUSession)
        with patch.object(sessions, "dll_wgfmu") as driver:
            driver.WGFMU_abort.return_value = 0
            with self.assertRaisesRegex(TimeoutError, "abort did not complete"):
                session.abort(timeout_s=0)

    def test_b1500_abort_still_runs_when_wgfmu_abort_fails(self):
        session = sessions.B1500Session.__new__(sessions.B1500Session)
        session.session = 1
        session._wgfmu = Mock()
        session._wgfmu.abort.side_effect = RuntimeError("WGFMU failed")
        session._check_ret = Mock()
        with patch.object(sessions, "dll_b1500") as driver:
            with self.assertRaises(ExceptionGroup):
                session.abort_measure()
            driver.agb1500_abortMeasure.assert_called_once_with(1)

    def test_bulk_samples_preserve_returned_count_and_pairs(self):
        session = sessions.WGFMUSession.__new__(sessions.WGFMUSession)
        def read(channel, index, size, times, values):
            self.assertEqual((channel, index), (101, 50))
            self.assertEqual(ct.cast(size, ct.POINTER(ct.c_int))[0], 4)
            ct.cast(size, ct.POINTER(ct.c_int))[0] = 2
            times[0], times[1] = .1, .2
            values[0], values[1] = 1., 2.
            return 0
        with patch.object(sessions, "dll_wgfmu") as driver:
            driver.WGFMU_getMeasureValues.side_effect = read
            self.assertEqual(session.read_chunk(101, 50, 4), [(.1, 1.), (.2, 2.)])
            driver.WGFMU_getMeasureValues.assert_called_once()
