import ctypes as ct
import unittest
from unittest.mock import Mock, patch

from instrumentio import sessions


class SessionTests(unittest.TestCase):
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
        with patch.object(sessions, "dll_b1500") as driver:
            with self.assertRaises(ExceptionGroup) as caught:
                session.close()
            self.assertEqual(len(caught.exception.exceptions), 2)
            session.zero_output.assert_called_once()
            session.set_switch.assert_called_once()
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
