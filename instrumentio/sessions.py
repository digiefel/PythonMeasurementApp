"""High-level instrument sessions built on top of low-level ctypes bindings."""

import ctypes as ct
import warnings

from .bindings import (
    ViInt16,
    ViInt32,
    ViPBoolean,
    ViPInt16,
    ViPInt32,
    ViPReal64,
    ViReal32,
    ViReal64,
    ViRsrc,
    ViSession,
    ViString,
    VI_ATTR_TERMCHAR,
    VI_ATTR_TERMCHAR_EN,
    dll_b1500,
    dll_visa32,
    dll_wgfmu,
)
from .codes import (
    B1500_AUTO_RANGE,
    B1500_CH_ALL,
    B1500_CH_NOCH,
    B1500_CMU_CORR_LOAD,
    B1500_CMU_CORR_OPEN,
    B1500_CMU_CORR_SHORT,
    B1500_IF_MODE,
    B1500_IM_MODE,
    B1500_INSTR_ERROR_DETECTED,
    B1500_LAST_STOP,
    B1500_MEAS_TYPE_SWEEP,
    B1500_STOP_DISABLE,
    B1500_VF_MODE,
    B1500_VM_MODE,
    WGFMU_STATUS_ABORTED,
    WGFMU_STATUS_ABORT_COMPLETED,
    WGFMU_STATUS_COMPLETED,
    WGFMU_STATUS_DONE,
    WGFMU_STATUS_RUNNING,
)
from .descriptors import describe_data_type, describe_data_type_short, describe_status_bits
from .parsers import parse_csv_floats, parse_fmt5_item, parse_scpi_status


def _module_has_asu(model: str) -> bool:
    text = (model or "").upper()
    return "E5288" in text or "ASU" in text


def _module_kind(model: str) -> str:
    text = (model or "").upper()
    if _module_has_asu(model):
        return "SMU"
    if "SMU" in text or any(token in text for token in ("B1510", "B1511", "B1512", "B1514", "B1517", "B1518", "E5281", "E5287", "E5290", "E5291")):
        return "SMU"
    if "WGFMU" in text or "B1530" in text:
        return "WGFMU"
    if "MFCMU" in text or "B1520" in text:
        return "CMU"
    return "UNKNOWN"


def _is_mainframe_model(model: str) -> bool:
    text = (model or "").upper()
    return any(token in text for token in ("B1500", "B1505", "E5270", "E5260"))


def _is_empty_module_model(model: str) -> bool:
    text = (model or "").strip().upper()
    return text in ("", "0", "NONE", "NULL", "EMPTY", "N/A", "NA")


class B1500Session:
    """
    High-level wrapper for B1500 instrument using ctypes bindings.
    """
    def __init__(self, gpib_addr="GPIB0::17::INSTR"):
        if not dll_b1500:
            raise RuntimeError("B1500 DLL not loaded.")
        self.gpib_addr = gpib_addr
        self.session = ViSession()
        self._wgfmu = None  # Lazy-loaded WGFMU session
        ret = dll_b1500.agb1500_init(gpib_addr.encode(), 1, 1, ct.byref(self.session))
        if ret != 0:
            raise RuntimeError(f"B1500 init failed: {ret}")

    def _visa_write(self, command: str):
        buf = command.encode("ascii")
        ret_count = ct.c_uint32(0)
        status = dll_visa32.viWrite(self.session, buf, len(buf), ct.byref(ret_count))
        if status < 0:
            raise RuntimeError(f"viWrite failed: {status}")

    def _visa_read(self, max_bytes: int = 4096) -> str:
        buf = ct.create_string_buffer(max_bytes)
        ret_count = ct.c_uint32(0)
        status = dll_visa32.viRead(self.session, buf, max_bytes, ct.byref(ret_count))
        if status < 0:
            raise RuntimeError(f"viRead failed: {status}")
        return buf.raw[:ret_count.value].decode("ascii")

    def _visa_query(self, command: str, max_bytes: int = 4096) -> str:
        if not command.endswith("\n"):
            command = f"{command}\n"
        self._visa_write(command)
        return self._visa_read(max_bytes)

    def _visa_set_termchar(self, char_code: int, enabled: bool = True):
        dll_visa32.viSetAttribute(self.session, VI_ATTR_TERMCHAR, char_code)
        dll_visa32.viSetAttribute(self.session, VI_ATTR_TERMCHAR_EN, 1 if enabled else 0)

    def discover_modules(self) -> dict:
        """Query installed B1500 modules and derive friendly channel maps.

        ``UNT? 1`` reports mainframe/module model strings. Some firmware includes
        the mainframe as the first entry, followed by slot 1; others report only
        slot entries. The parser handles both forms.
        """
        raw = self._visa_query("UNT? 1", max_bytes=8192).strip()
        compact = raw.replace("\r", "").replace("\n", "")
        entries = [entry.strip() for entry in compact.split(";") if entry.strip()]
        mainframe = None
        modules = []
        has_mainframe_entry = False

        if entries:
            first_model = entries[0].split(",", 1)[0].strip()
            has_mainframe_entry = _is_mainframe_model(first_model)

        for index, entry in enumerate(entries):
            parts = [part.strip() for part in entry.split(",")]
            model = parts[0] if parts else ""
            revision = ",".join(parts[1:]) if len(parts) > 1 else ""
            if index == 0 and has_mainframe_entry:
                mainframe = {"model": model, "revision": revision}
                continue
            if _is_empty_module_model(model):
                continue
            slot = index if has_mainframe_entry else index + 1
            modules.append(
                {
                    "slot": slot,
                    "channel": slot,
                    "model": model,
                    "revision": revision,
                    "kind": _module_kind(model),
                    "has_asu": _module_has_asu(model),
                }
            )

        smu_modules = [module for module in modules if module["kind"] == "SMU"]
        smu_channel_map = {
            f"SMU{idx}": module["channel"]
            for idx, module in enumerate(sorted(smu_modules, key=lambda item: item["slot"]), start=1)
        }
        asu_channel_map = {
            label: channel
            for label, channel in smu_channel_map.items()
            if any(module["channel"] == channel and module.get("has_asu") for module in smu_modules)
        }
        return {
            "raw": raw,
            "mainframe": mainframe,
            "modules": modules,
            "smu_channel_map": smu_channel_map,
            "asu_channel_map": asu_channel_map,
        }

    @property
    def wgfmu(self):
        """Get or create the WGFMU session (lazy initialization)."""
        if self._wgfmu is None:
            self._wgfmu = WGFMUSession(self.gpib_addr)
        return self._wgfmu

    def error_query(self):
        """Return (error_number, error_message) from instrument."""
        errnum = ViInt32()
        errmsg = ct.create_string_buffer(256)
        ret = dll_b1500.agb1500_error_query(self.session, ct.byref(errnum), errmsg)
        if ret != 0:
            raise RuntimeError(f"Error query failed: {ret}")
        return errnum.value, errmsg.value.decode(errors='ignore').strip()

    def _describe_status(self, ret):
        """Return human-readable description for a driver status code."""
        try:
            buf = ct.create_string_buffer(256)
            dll_b1500.agb1500_error_message(self.session, ret, buf)
            msg = buf.value.decode(errors="ignore").strip()
            return msg
        except Exception:
            return ""

    def _check_ret(self, ret, context):
        if ret == B1500_INSTR_ERROR_DETECTED:
            errnum, errmsg = self.error_query()
            raise RuntimeError(f"{context}: instrument error {errnum}: {errmsg} (ret={ret})")
        if ret < 0:
            msg = self._describe_status(ret)
            raise RuntimeError(f"{context} failed: {ret} {f'({msg})' if msg else ''}".strip())
        if ret != 0:
            raise RuntimeError(f"{context} failed: {ret}")

    def reset(self):
        dll_b1500.agb1500_reset(self.session)

    def set_timeout(self, ms):
        dll_b1500.agb1500_timeOut(self.session, ms)

    def enable_error_detect(self, enable):
        dll_b1500.agb1500_errorQueryDetect(self.session, 1 if enable else 0)

    def set_switch(self, channel, state):
        """Control switch matrix channel on/off state."""
        ret = dll_b1500.agb1500_setSwitch(self.session, channel, 1 if state else 0)
        self._check_ret(ret, "Set switch")

    def reset_timestamp(self):
        """Reset internal timestamp for measurements."""
        ret = dll_b1500.agb1500_resetTimestamp(self.session)
        if ret != 0:
            raise RuntimeError(f"Reset timestamp failed: {ret}")

    def stop_mode(self, stop=B1500_STOP_DISABLE, last_mode=B1500_LAST_STOP):
        """
        Configure stop behavior. Set stop=STOP_DISABLE to prevent the instrument from
        aborting the sweep on compliance; last_mode controls post-stop output level.
        """
        ret = dll_b1500.agb1500_stopMode(self.session, stop, last_mode)
        self._check_ret(ret, "Stop mode")

    def force_current(self, channel, current, compliance=10.0, range_=B1500_AUTO_RANGE, polarity=0):
        """Force a current level on the specified channel."""
        ret = dll_b1500.agb1500_force(self.session, channel, B1500_IF_MODE, range_, current, compliance, polarity)
        self._check_ret(ret, "Force current")

    def force_voltage(self, channel, voltage, compliance=0.1, range_=B1500_AUTO_RANGE, polarity=0):
        """Force a voltage level on the specified channel."""
        ret = dll_b1500.agb1500_force(self.session, channel, B1500_VF_MODE, range_, voltage, compliance, polarity)
        self._check_ret(ret, "Force voltage")

    def asu_path(self, channel, path):
        """Select ASU path for a channel (see B1500 ASU path modes)."""
        ret = dll_b1500.agb1500_asuPath(self.session, channel, path)
        self._check_ret(ret, "ASU path")

    def asu_range(self, channel, rng):
        """Select ASU range for a channel (see B1500 ASU ranges)."""
        ret = dll_b1500.agb1500_asuRange(self.session, channel, rng)
        self._check_ret(ret, "ASU range")

    def asu_led(self, channel, on):
        """Control ASU LED (optional helper)."""
        ret = dll_b1500.agb1500_asuLed(self.session, channel, 1 if on else 0)
        self._check_ret(ret, "ASU LED")

    def set_iv_sweep(self, channel, sweep_mode, range_, start, stop, points, hold=0.0, delay=0.0, second_delay=0.0, compliance=10.0, power_compliance=0.0):
        """
        Configure a source sweep on a single channel.
        For current sweeps use sweep_mode=SWP_IF_SGLLIN and range_ as the source current range.
        For voltage sweeps use sweep_mode=SWP_VF_SGLLIN and range_ as the source voltage range.
        """
        ret = dll_b1500.agb1500_setIv(self.session, channel, sweep_mode, range_, start, stop, points, hold, delay, second_delay, compliance, power_compliance)
        self._check_ret(ret, "Set IV sweep")

    def set_sweep_sync(self, channel, output_mode, range_, start, stop, compliance=10.0, power_compliance=0.0):
        """
        Configure a synchronous sweep source.
        output_mode must match the primary sweep output mode: B1500_IF_MODE for
        current sweeps or B1500_VF_MODE for voltage sweeps.
        """
        ret = dll_b1500.agb1500_setSweepSync(
            self.session,
            channel,
            output_mode,
            range_,
            start,
            stop,
            compliance,
            power_compliance,
        )
        self._check_ret(ret, "Set synchronous sweep")

    def sweep_iv(self, channel, measurement_mode, measurement_range, expected_points):
        """Execute configured sweep on channel and return measurement data."""
        source = (ViReal64 * expected_points)()
        value = (ViReal64 * expected_points)()
        status = (ViInt32 * expected_points)()
        time_ = (ViReal64 * expected_points)()
        point_count = ViInt32(expected_points)
        ret = dll_b1500.agb1500_sweepIv(self.session, channel, measurement_mode, measurement_range, ct.byref(point_count), source, value, status, time_)
        self._check_ret(ret, "Sweep IV")
        return list(source)[:point_count.value], list(value)[:point_count.value], list(status)[:point_count.value], list(time_)[:point_count.value], point_count.value

    def sweep_miv(self, channels, modes, ranges, expected_points):
        """Execute a sweep and measure multiple channels per point (agb1500_sweepMiv)."""
        n = len(channels)
        ch_arr = (ViInt32 * n)(*channels)
        mode_arr = (ViInt32 * n)(*modes)
        range_arr = (ViReal64 * n)(*ranges)
        total_points = expected_points * n
        source = (ViReal64 * total_points)()
        value = (ViReal64 * total_points)()
        status = (ViInt32 * total_points)()
        time_ = (ViReal64 * total_points)()
        point_count = ViInt32(expected_points)
        ret = dll_b1500.agb1500_sweepMiv(self.session, ch_arr, mode_arr, range_arr, ct.byref(point_count), source, value, status, time_)
        self._check_ret(ret, "Sweep MIV")
        data = {}
        for i, ch in enumerate(channels):
            start = i * point_count.value
            end = start + point_count.value
            data[ch] = {
                "source": list(source)[start:end],
                "value": list(value)[start:end],
                "status": list(status)[start:end],
                "time": list(time_)[start:end],
            }
        return data, point_count.value

    def force_cmu_dc_bias(self, channel, value):
        """Force a DC bias on the CMU channel."""
        ret = dll_b1500.agb1500_forceCmuDcBias(self.session, channel, value)
        self._check_ret(ret, "Force CMU DC bias")

    def set_cmu_integ(self, mode, value):
        """Set CMU integration mode/value (see agb1500_INTEG_* constants)."""
        ret = dll_b1500.agb1500_setCmuInteg(self.session, mode, value)
        self._check_ret(ret, "Set CMU integration")

    def force_cmu_ac_level(self, channel, value):
        """Set CMU AC test level."""
        ret = dll_b1500.agb1500_forceCmuAcLevel(self.session, channel, value)
        self._check_ret(ret, "Force CMU AC level")

    def set_cmu_freq(self, channel, frequency_hz):
        """Set CMU measurement frequency."""
        ret = dll_b1500.agb1500_setCmuFreq(self.session, channel, frequency_hz)
        self._check_ret(ret, "Set CMU frequency")

    def set_cv(self, channel, mode, start, stop, points, hold=0.0, delay=0.0, second_delay=0.0):
        """Configure a C-V sweep on the CMU."""
        ret = dll_b1500.agb1500_setCv(
            self.session,
            channel,
            mode,
            start,
            stop,
            points,
            hold,
            delay,
            second_delay,
        )
        self._check_ret(ret, "Set C-V sweep")

    def spot_cmu_meas(self, channel, mode, range_=B1500_AUTO_RANGE):
        """Single CMU measurement point.

        Returns (primary, status, monitor, status_monitor, timestamp).
        """
        data = ViReal64()
        status = ViInt32()
        monitor = ViReal64()
        status_mon = ViInt32()
        time_ = ViReal64()
        ret = dll_b1500.agb1500_spotCmuMeas(
            self.session,
            channel,
            mode,
            range_,
            ct.byref(data),
            ct.byref(status),
            ct.byref(monitor),
            ct.byref(status_mon),
            ct.byref(time_),
        )
        self._check_ret(ret, "Spot CMU measurement")
        return data.value, status.value, monitor.value, status_mon.value, time_.value

    def sweep_cv(self, channel, mode, measurement_range, expected_points):
        """Execute configured C-V sweep and return arrays with point_count.

        The DLL reports point_count = N (number of bias points) but writes
        2*N entries into value[], status[], monitor[], and status_mon[] -
        interleaving the two measurement components per bias point:
          value[2i]   = primary component (e.g. Cp)
          value[2i+1] = secondary component (e.g. Rp)
        source[] and time[] have exactly N entries (one per bias point).
        This method returns the full 2*N slice for value/status/monitor arrays.
        """
        expected = max(1, int(expected_points))
        # source/time: N entries; value/status/monitor: 2*N entries.
        cap_source = min(200000, max(expected + 64, expected * 2))
        cap_values = min(400000, max(expected * 2 + 64, expected * 3))

        source = (ViReal64 * cap_source)()
        value = (ViReal64 * cap_values)()
        status = (ViInt32 * cap_values)()
        monitor = (ViReal64 * cap_values)()
        status_mon = (ViInt32 * cap_values)()
        time_ = (ViReal64 * cap_source)()
        point_count = ViInt32(cap_source)
        ret = dll_b1500.agb1500_sweepCv(
            self.session,
            channel,
            mode,
            measurement_range,
            ct.byref(point_count),
            source,
            value,
            status,
            monitor,
            status_mon,
            time_,
        )
        self._check_ret(ret, "Sweep C-V")
        count = point_count.value
        if count < 0 or count > cap_source:
            raise RuntimeError(
                f"Sweep C-V returned invalid point_count={count} for capacity={cap_source}."
            )
        return (
            list(source)[:count],
            list(value)[:2 * count],
            list(status)[:2 * count],
            list(monitor)[:2 * count],
            list(status_mon)[:2 * count],
            list(time_)[:count],
            count,
        )

    def zero_output(self, channel):
        """Return channel to zero output state."""
        ret = dll_b1500.agb1500_zeroOutput(self.session, channel)
        self._check_ret(ret, "Zero output")

    def abort_measure(self):
        """Abort ongoing measurement/sweep on B1500 and WGFMU."""
        # Abort WGFMU first if it was used
        if self._wgfmu is not None:
            try:
                self._wgfmu.abort()
            except Exception:
                pass
        dll_b1500.agb1500_abortMeasure(self.session)

    def spot_meas(self, channel, mode, range_=B1500_AUTO_RANGE):
        """Single spot measurement on a channel."""
        value = ViReal64()
        status = ViInt32()
        timestamp = ViReal64()
        ret = dll_b1500.agb1500_spotMeas(self.session, channel, mode, range_, ct.byref(value), ct.byref(status), ct.byref(timestamp))
        self._check_ret(ret, "Spot measurement")
        return value.value, status.value, timestamp.value

    def start_measure(self, channels, modes, ranges, source_output=1, timestamp=1, monitor=0, meas_type=B1500_MEAS_TYPE_SWEEP):
        """
        Begin a measurement to enable streaming via read_data.
        startMeasure expects channel array terminated by 0. The source_output flag controls whether source data is reported.
        """
        ch_list = list(channels) + [0]
        mode_list = list(modes) + [0]
        range_list = list(ranges) + [0.0]
        ch_arr = (ViInt32 * len(ch_list))(*ch_list)
        mode_arr = (ViInt32 * len(mode_list))(*mode_list)
        range_arr = (ViReal64 * len(range_list))(*range_list)
        ret = dll_b1500.agb1500_startMeasure(self.session, meas_type, ch_arr, mode_arr, range_arr, source_output, timestamp, monitor)
        self._check_ret(ret, "Start measure")

    def read_data(self):
        """Read one measurement record from the streaming buffer.

        Returns (ret, eod, data_type, value, status, channel)
        - ret: driver return (can be -1 while data are valid; do not treat as fatal mid-measurement)
        - eod: End Of Data flag (1=data end, 0=data available)
        - data_type codes:
            1  Current measurement data
            2  Voltage measurement data
            3  Current output data
            4  Voltage output data
            5  Time stamp data
            6  Impedance (R-X) measurement data
            7  Admittance (G-B) measurement data
            8  Capacitance measurement data
            9  Dissipation factor measurement data
            10 Quality factor measurement data
            11 Inductance measurement data
            12 Phase measurement data (radian)
            13 Phase measurement data (degree)
            14 Frequency data
            15 Sampling index
            16 Invalid data
        - value: Measured data or source setup data.
        - status: Measurement status bitstring (compliance/overflow/etc).
        - channel: Channel number that generated this data (-1 means no channel).

        Notes on error handling (Keysight guidance):
        * The driver issues *OPC? internally; when the instrument is still busy this can time out and return -1 even
          though the data/status are valid. Do not abort on a lone -1.
        * ret < 0 should be logged as a driver/GPIB issue, separate from measurement quality (status bits).
        * Avoid calling error_query while streaming; it can hang the instrument.
        """
        eod = ViInt32()
        data_type = ViInt32()
        value = ViReal64()
        status = ViInt32()
        channel = ViInt32()
        ret = dll_b1500.agb1500_readData(self.session, ct.byref(eod), ct.byref(data_type), ct.byref(value), ct.byref(status), ct.byref(channel))
        # Do not call _check_ret here; caller decides how to handle transient negatives.
        return ret, eod.value, data_type.value, value.value, status.value, channel.value

    def stream_cv_sweep(self, cmu_channel, cmu_mode, meas_range, expected_points, callback):
        """Execute a CV sweep via raw SCPI with per-point streaming.

        Uses FMT 5,0 (comma terminator) + XE and reads five FMT5 tokens per point:
        Time, Para1, Para2, OscLevel, DCBias.

        Args:
            cmu_channel: CMU channel number.
            cmu_mode: IMP mode code (e.g. 100 for Cp-G).
            meas_range: Measurement range (0 = auto).
            expected_points: Number of sweep steps to read.
            callback: Called as callback(step, dc_bias_v, para1, para2, time_s, s1, s2)
                      after each step completes.
        """
        # Set comma-terminated format, timestamp, monitor
        self._visa_write("FMT 5,0\n")
        self._visa_write("TSC 1\n")
        self._visa_write("LMN 1\n")
        # Measurement mode = CV DC bias sweep
        self._visa_write(f"MM 18,{cmu_channel}\n")
        self._visa_write(f"IMP {cmu_mode}\n")
        meas_range_int = int(meas_range) if meas_range == int(meas_range) else meas_range
        self._visa_write(f"RC {cmu_channel},{meas_range_int}\n")
        # Reset timestamp and trigger
        self._visa_write("TSR\n")

        # Set VISA termination character to comma (ASCII 44)
        self._visa_set_termchar(44, True)

        try:
            self._visa_write("XE\n")

            def _read_token():
                return parse_fmt5_item(self._visa_read(64))

            for step in range(expected_points):
                # MM18 + LMN1 order: Time, Para1, Para2, Osc, DCBias.
                _ts, _tc, time_type, time_s = _read_token()
                p1_status, _c1, _t1, para1 = _read_token()
                p2_status, _c2, _t2, para2 = _read_token()
                _os, _oc, _ot, _ov = _read_token()
                _ds, _dc, _dt, dc_bias_v = _read_token()

                if time_type != 'T':
                    raise RuntimeError(
                        f"Unexpected CV stream layout at step {step}: first token type={time_type!r}, expected 'T'"
                    )

                callback(
                    step,
                    dc_bias_v,
                    para1,
                    para2,
                    time_s,
                    parse_scpi_status(p1_status),
                    parse_scpi_status(p2_status),
                )
        finally:
            # Restore normal termination (newline)
            self._visa_set_termchar(10, True)

    @staticmethod
    def _normalize_corr_type(corr_type) -> int:
        if isinstance(corr_type, str):
            key = corr_type.strip().lower()
            mapping = {
                "open": B1500_CMU_CORR_OPEN,
                "o": B1500_CMU_CORR_OPEN,
                "short": B1500_CMU_CORR_SHORT,
                "s": B1500_CMU_CORR_SHORT,
                "load": B1500_CMU_CORR_LOAD,
                "l": B1500_CMU_CORR_LOAD,
            }
            if key not in mapping:
                raise ValueError(f"Unsupported correction type: {corr_type!r}")
            return mapping[key]
        corr = int(corr_type)
        if corr not in (B1500_CMU_CORR_OPEN, B1500_CMU_CORR_SHORT, B1500_CMU_CORR_LOAD):
            raise ValueError(f"Unsupported correction type code: {corr}")
        return corr

    def _set_corr_mode_enabled(self, channel: int, corr: int, enabled: bool) -> None:
        # DLL API uses 0 = ON, 1 = OFF for correction mode.
        state = 0 if enabled else 1
        if corr == B1500_CMU_CORR_OPEN:
            ret = dll_b1500.agb1500_setOpenCorrMode(self.session, int(channel), state)
            self._check_ret(ret, "Set open correction mode")
            return
        if corr == B1500_CMU_CORR_SHORT:
            ret = dll_b1500.agb1500_setShortCorrMode(self.session, int(channel), state)
            self._check_ret(ret, "Set short correction mode")
            return
        if corr == B1500_CMU_CORR_LOAD:
            ret = dll_b1500.agb1500_setLoadCorrMode(self.session, int(channel), state)
            self._check_ret(ret, "Set load correction mode")
            return
        raise ValueError(f"Unsupported correction type code: {corr}")

    def run_cmu_phase_compensation(self, channel: int, mode: int = 1) -> dict:
        """Execute CMU phase compensation and return raw/parsed result metadata."""
        ch = int(channel)
        mode_i = int(mode)
        ret = dll_b1500.agb1500_setCmuAdjustMode(self.session, ch, mode_i)
        self._check_ret(ret, "Set CMU adjust mode")
        ret = dll_b1500.agb1500_setSwitch(self.session, ch, 1)
        self._check_ret(ret, "Set channel output switch ON")
        result = ViInt16(0)
        ret = dll_b1500.agb1500_execCmuAdjust(self.session, ch, ct.byref(result))
        self._check_ret(ret, "Execute CMU phase compensation")
        raw_adj = self._visa_query(f"ADJ? {ch},{mode_i}")
        return {
            "channel": ch,
            "mode": mode_i,
            "result": int(result.value),
            "adj_query": raw_adj.strip(),
        }

    def get_cmu_phase_compensation_result(self, channel: int, mode: int = 0) -> int:
        """Return ADJ? result code for phase compensation state.

        mode=0 reuses the last phase compensation data without performing
        a new measurement (manual-defined behavior per programming guide).
        """
        ch = int(channel)
        mode_i = int(mode)
        raw = self._visa_query(f"ADJ? {ch},{mode_i}").strip()
        try:
            # Be tolerant of responses with extra text or separators.
            token = raw.split(',')[0].split()[0]
            return int(float(token))
        except Exception as e:
            raise RuntimeError(f"Unexpected ADJ? response: {raw!r}") from e

    def get_cmu_correction_count(self, channel: int) -> int:
        """Return number of correction-frequency entries currently stored in the CMU list."""
        resp = self._visa_query(f"CORRL? {int(channel)}")
        return int(float(resp.strip()))

    def get_cmu_correction_frequency(self, channel: int, index: int) -> float:
        """Return correction frequency (Hz) at index (1-based)."""
        resp = self._visa_query(f"CORRL? {int(channel)},{int(index)}")
        return float(resp.strip())

    def get_cmu_correction_data(self, channel: int, index: int) -> dict:
        """Return full correction coefficients from CORRDT? for a list index."""
        raw = self._visa_query(f"CORRDT? {int(channel)},{int(index)}")
        vals = parse_csv_floats(raw)
        if len(vals) != 7:
            raise RuntimeError(f"Unexpected CORRDT? response: {raw!r}")
        return {
            "index": int(index),
            "frequency_hz": vals[0],
            "open_r": vals[1],
            "open_i": vals[2],
            "short_r": vals[3],
            "short_i": vals[4],
            "load_r": vals[5],
            "load_i": vals[6],
            "raw": raw.strip(),
        }

    def get_cmu_correction_data_for_frequency(self, channel: int, frequency_hz: float, tolerance_hz: float = 1.0) -> dict:
        """Return CORRDT data for a frequency entry; matches by absolute tolerance."""
        ch = int(channel)
        target = float(frequency_hz)
        count = self.get_cmu_correction_count(ch)
        if count < 1:
            raise RuntimeError("No correction frequency entries found.")
        for idx in range(1, count + 1):
            freq = self.get_cmu_correction_frequency(ch, idx)
            if abs(freq - target) <= tolerance_hz:
                return self.get_cmu_correction_data(ch, idx)
        raise RuntimeError(
            f"No correction data found for frequency {target:.6g} Hz on channel {ch}."
        )

    def run_cmu_correction(
        self,
        channel: int,
        corr_type,
        frequency_hz: float,
        mode: int | None = None,
        primary: float = 0.0,
        secondary: float | None = None,
    ) -> dict:
        """Run open/short/load CMU correction and return result + stored coefficients."""
        ch = int(channel)
        corr = self._normalize_corr_type(corr_type)
        freq = float(frequency_hz)

        if mode is None:
            mode = 100 if corr == B1500_CMU_CORR_OPEN else 400
        mode_i = int(mode)

        if secondary is None:
            secondary = 0.0 if corr == B1500_CMU_CORR_OPEN else 50.0

        ret = dll_b1500.agb1500_setSwitch(self.session, ch, 1)
        self._check_ret(ret, "Set channel output switch ON")
        self._set_corr_mode_enabled(ch, corr, True)

        corr_result = ViInt16(0)
        if corr == B1500_CMU_CORR_OPEN:
            ret = dll_b1500.agb1500_execOpenCorr(
                self.session,
                ch,
                freq,
                mode_i,
                float(primary),
                float(secondary),
                ct.byref(corr_result),
            )
            self._check_ret(ret, "Execute open correction")
        elif corr == B1500_CMU_CORR_SHORT:
            ret = dll_b1500.agb1500_execShortCorr(
                self.session,
                ch,
                freq,
                mode_i,
                float(primary),
                float(secondary),
                ct.byref(corr_result),
            )
            self._check_ret(ret, "Execute short correction")
        else:
            ret = dll_b1500.agb1500_execLoadCorr(
                self.session,
                ch,
                freq,
                mode_i,
                float(primary),
                float(secondary),
                ct.byref(corr_result),
            )
            self._check_ret(ret, "Execute load correction")

        if int(corr_result.value) != 0:
            state_text = {1: "failed", 2: "aborted"}.get(int(corr_result.value), f"code {int(corr_result.value)}")
            raise RuntimeError(f"CMU correction returned {state_text}")

        # Query correction enable states to keep UI in sync with instrument state.
        states = {
            "open": int(float(self._visa_query(f"CORRST? {ch},1").strip())),
            "short": int(float(self._visa_query(f"CORRST? {ch},2").strip())),
            "load": int(float(self._visa_query(f"CORRST? {ch},3").strip())),
        }

        coeffs = self.get_cmu_correction_data_for_frequency(ch, freq)
        return {
            "channel": ch,
            "corr_type": corr,
            "frequency_hz": freq,
            "mode": mode_i,
            "primary_reference": float(primary),
            "secondary_reference": float(secondary),
            "result": int(corr_result.value),
            "corr_state": states,
            "coefficients": coeffs,
        }

    def close(self):
        # Close WGFMU session first if it was used
        if self._wgfmu is not None:
            try:
                self._wgfmu.close()
            except Exception:
                pass
            self._wgfmu = None
        dll_b1500.agb1500_close(self.session)


class WGFMUSession:
    """
    High-level wrapper for WGFMU instrument using ctypes bindings.
    """

    def __init__(self, address: str | None = None):
        if not dll_wgfmu:
            raise RuntimeError("WGFMU DLL not loaded.")
        if address is not None:
            ret = dll_wgfmu.WGFMU_openSession(address.encode())
            self._check_ret(ret, "WGFMU open session")
        ret = dll_wgfmu.WGFMU_clear()
        self._check_ret(ret, "WGFMU initialize")

    def _get_error_summary(self) -> str | None:
        try:
            size = ct.c_int()
            ret = dll_wgfmu.WGFMU_getErrorSummarySize(ct.byref(size))
            if ret < 0 or size.value <= 0:
                return None
            buf = ct.create_string_buffer(size.value)
            ret = dll_wgfmu.WGFMU_getErrorSummary(buf, ct.byref(size))
            if ret < 0:
                return None
            text = buf.value.decode(errors="replace").strip()
            return text or None
        except Exception:
            return None

    def _get_warning_summary(self) -> str | None:
        try:
            size = ct.c_int()
            ret = dll_wgfmu.WGFMU_getWarningSummarySize(ct.byref(size))
            if ret < 0 or size.value <= 0:
                return None
            buf = ct.create_string_buffer(size.value)
            ret = dll_wgfmu.WGFMU_getWarningSummary(buf, ct.byref(size))
            if ret < 0:
                return None
            text = buf.value.decode(errors="replace").strip()
            return text or None
        except Exception:
            return None

    def _check_ret(self, ret, context):
        # WGFMU returns:
        #   ret < 0  => error
        #   ret == 0 => OK
        #   ret > 0  => warning (non-fatal)
        if ret < 0:
            detail = self._get_error_summary()
            if detail:
                raise RuntimeError(f"{context} failed: {ret}. {detail}")
            raise RuntimeError(f"{context} failed: {ret}")
        if ret > 0:
            detail = self._get_warning_summary()
            if detail:
                warnings.warn(f"{context}: {detail} (code {ret})", RuntimeWarning)
            else:
                warnings.warn(f"{context}: warning code {ret}", RuntimeWarning)

    def close(self):
        ret = dll_wgfmu.WGFMU_closeSession()
        self._check_ret(ret, "WGFMU close session")

    def clear(self):
        ret = dll_wgfmu.WGFMU_clear()
        self._check_ret(ret, "WGFMU clear")

    def initialize(self):
        ret = dll_wgfmu.WGFMU_initialize()
        self._check_ret(ret, "WGFMU initialize")

    def connect(self, channel_id: int):
        ret = dll_wgfmu.WGFMU_connect(channel_id)
        self._check_ret(ret, "WGFMU connect")

    def disconnect(self, channel_id: int):
        ret = dll_wgfmu.WGFMU_disconnect(channel_id)
        self._check_ret(ret, "WGFMU disconnect")

    def set_operation_mode(self, channel_id: int, mode: int):
        ret = dll_wgfmu.WGFMU_setOperationMode(channel_id, mode)
        self._check_ret(ret, "WGFMU set operation mode")

    def set_force_voltage_range(self, channel_id: int, rng: int):
        ret = dll_wgfmu.WGFMU_setForceVoltageRange(channel_id, rng)
        self._check_ret(ret, "WGFMU set force voltage range")

    def set_measure_mode(self, channel_id: int, mode: int):
        ret = dll_wgfmu.WGFMU_setMeasureMode(channel_id, mode)
        self._check_ret(ret, "WGFMU set measure mode")

    def set_measure_voltage_range(self, channel_id: int, rng: int):
        ret = dll_wgfmu.WGFMU_setMeasureVoltageRange(channel_id, rng)
        self._check_ret(ret, "WGFMU set measure voltage range")

    def set_measure_current_range(self, channel_id: int, rng: int):
        ret = dll_wgfmu.WGFMU_setMeasureCurrentRange(channel_id, rng)
        self._check_ret(ret, "WGFMU set measure current range")

    def set_measure_enabled(self, channel_id: int, enabled: int):
        ret = dll_wgfmu.WGFMU_setMeasureEnabled(channel_id, enabled)
        self._check_ret(ret, "WGFMU set measure enabled")

    def set_measure_event(
        self,
        pattern_name: str,
        event_name: str,
        time: float,
        measurement_points: int,
        measurement_interval: float,
        averaging_time: float,
        raw_data: int,
    ):
        ret = dll_wgfmu.WGFMU_setMeasureEvent(
            pattern_name.encode(),
            event_name.encode(),
            time,
            measurement_points,
            measurement_interval,
            averaging_time,
            raw_data,
        )
        self._check_ret(ret, "WGFMU set measure event")

    def create_pattern(self, name, initial_voltage=0.0):
        ret = dll_wgfmu.WGFMU_createPattern(name.encode(), initial_voltage)
        self._check_ret(ret, "WGFMU create pattern")

    def add_vector(self, pattern_name, time, voltage):
        ret = dll_wgfmu.WGFMU_addVector(pattern_name.encode(), time, voltage)
        self._check_ret(ret, "WGFMU add vector")

    def add_sequence(self, channel_id, pattern_name, repetitions):
        ret = dll_wgfmu.WGFMU_addSequence(channel_id, pattern_name.encode(), repetitions)
        self._check_ret(ret, "WGFMU add sequence")

    def execute(self):
        ret = dll_wgfmu.WGFMU_execute()
        self._check_ret(ret, "WGFMU execute")

    def get_status(self):
        """Get execution status. Returns (status_code, elapsed_time, total_time)."""
        status = ct.c_int()
        elapsed = ct.c_double()
        total = ct.c_double()
        ret = dll_wgfmu.WGFMU_getStatus(ct.byref(status), ct.byref(elapsed), ct.byref(total))
        self._check_ret(ret, "WGFMU get status")
        return status.value, elapsed.value, total.value

    def get_measure_value_size(self, channel_id):
        measured = ct.c_int()
        total = ct.c_int()
        ret = dll_wgfmu.WGFMU_getMeasureValueSize(channel_id, ct.byref(measured), ct.byref(total))
        self._check_ret(ret, "WGFMU get measure value size")
        return measured.value, total.value

    def get_measure_value(self, channel_id, index):
        time_ = ct.c_double()
        value = ct.c_double()
        ret = dll_wgfmu.WGFMU_getMeasureValue(channel_id, index, ct.byref(time_), ct.byref(value))
        self._check_ret(ret, "WGFMU get measure value")
        return time_.value, value.value

    def abort(self, timeout_s: float = 2.0):
        """Abort all WGFMU channels and wait for abort to complete."""
        ret = dll_wgfmu.WGFMU_abort()
        if ret < 0:
            return ret  # Already failed, don't wait

        # Wait for ABORT_COMPLETED or IDLE status
        import time

        start = time.time()
        while time.time() - start < timeout_s:
            try:
                status, _, _ = self.get_status()
                # 10003 = ABORT_COMPLETED, 10001 = IDLE, 10000 = COMPLETED
                if status in (10003, 10001, 10000):
                    return 0  # Success
            except Exception:
                pass
            time.sleep(0.01)
        return ret  # Timeout, return original result

    def abort_channel(self, channel_id: int):
        """Abort a specific WGFMU channel."""
        ret = dll_wgfmu.WGFMU_abortChannel(channel_id)
        return ret

    def poll(self, channel_1: int, channel_2: int):
        """Single-call status + available-sample-count query for two channels.

        Returns (status, elapsed, total, measured_1, total_1, measured_2, total_2).
        Reduces three per-tick RPC round-trips to one when called via the bridge.
        """
        status, elapsed, total = self.get_status()
        measured_1, total_1 = self.get_measure_value_size(channel_1)
        measured_2, total_2 = self.get_measure_value_size(channel_2)
        return status, elapsed, total, measured_1, total_1, measured_2, total_2
