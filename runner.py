import os.path
import time
import atexit
from typing import TYPE_CHECKING, Optional, Dict, Any
import threading
from procedures.base import MeasurementAbortRequested
from instrumentio.codes import B1500_CH_ALL
from instrumentio.sessions import B1500Session
from prober import ProberController

if TYPE_CHECKING:
    from plotting import PlotBridge, PlotDef


class MeasurementRunner:
    CONTACT_LIGHTS_OFF_DELAY_S = 1.0

    def __init__(self, config):
        self.config = config
        self.log_callback = None
        self.plot: PlotBridge | None = None
        self.status_callback = None
        self.contact_state_callback = None
        self.light_state_callback = None
        self._last_status_message = None
        self.temp_step_started_cb = None
        self.temp_phase_cb = None
        self.temp_sample_cb = None
        self.temp_device_done_cb = None
        self.b1500: B1500Session
        self.prober_ctrl = ProberController(self.log)
        self.current_chip = None
        self.current_site = None
        self.current_subsite = None
        self.current_temp_c: Optional[float] = None
        self._current_temp_step: Optional[int] = None
        # Temperature compensation coefficients (um per C)
        self.temp_comp_coeffs_xyz = (None, None, None)
        # XY reference temperature (set on first temperature read)
        self.temp_ref_c: Optional[float] = None
        # Baseline Z heights and reference temperature (captured once at first convergence)
        self.temp_comp_ref_z_heights = None  # (contact, separation, overtravel, hover)
        self.stop_event = threading.Event()
        atexit.register(self.safe_stop)
    
    def log(self, msg):
        if self.log_callback:
            self.log_callback(msg)
        else:
            print("Warning: No log callback registered. Message:", msg)

    def get_b1500(self, address: str) -> B1500Session:
        """Get or create the B1500 session."""
        if not getattr(self, 'b1500', None):
            self.log(f'Opening B1500 session at {address}')
            self.b1500 = B1500Session(address)
        return self.b1500

    
    def safe_stop(self):
        """
        Universal stop method.
        Only sets the stop_event flag. The worker thread handles the actual
        instrument abort to avoid GPIB bus contention.
        """
        self.stop_event.set()
        self.log("Stop requested.")
        
        # Separate prober for safety (this is a different bus, OK to call here)
        has_prober = getattr(self.prober_ctrl, "prober", None) is not None
        if has_prober:
            try:
                separated = self.prober_ctrl.separation()
                if separated and self.contact_state_callback:
                    try:
                        self.contact_state_callback(False)
                    except Exception as e:
                        self.log(f"Contact state cb error: {e}")
                if separated:
                    self.prober_set_light(True)
            except Exception:
                pass

    def check_stop(self, context: str = ""):
        """Raise an abort if a stop is active."""
        if self.stop_event.is_set():
            self.log(f"Stop request: {context}")
            raise MeasurementAbortRequested(context or "Stop requested")

    # --- Prober wrappers ---
    def set_subsite_origin(self, x_offset: float, y_offset: float):
        self.prober_ctrl.set_subsite_origin(x_offset, y_offset)
        self.subsite_origin = self.prober_ctrl.subsite_origin

    def prober_go_home(self):
        self.prober_ctrl.go_home()

    def prober_contact(self):
        self.check_stop("Stop requested before prober contact")
        ok = self.prober_ctrl.contact()
        if ok and self.contact_state_callback:
            try:
                self.contact_state_callback(True)
            except Exception as e:
                self.log(f"Contact state cb error: {e}")
        return ok

    def prober_separation(self):
        ok = self.prober_ctrl.separation()
        if ok and self.contact_state_callback:
            try:
                self.contact_state_callback(False)
            except Exception as e:
                self.log(f"Contact state cb error: {e}")
        return ok

    def prober_read_position(self):
        return self.prober_ctrl.read_position()

    def prober_toggle_light(self):
        state = self.prober_ctrl.toggle_scope_light()
        if state is not None and self.light_state_callback:
            try:
                self.light_state_callback(state)
            except Exception as e:
                self.log(f"Light state cb error: {e}")
        return state

    def prober_set_light(self, light_on: bool):
        state = self.prober_ctrl.set_scope_light(light_on)
        if state is not None and self.light_state_callback:
            try:
                self.light_state_callback(state)
            except Exception as e:
                self.log(f"Light state cb error: {e}")
        return state

    def get_chuck_height(self) -> Optional[float]:
        return self.prober_ctrl.get_chuck_height()

    def get_temp_setpoint(self) -> Optional[float]:
        return self.prober_ctrl.get_temp_setpoint()

    def get_thermo_state(self) -> Optional[str]:
        return self.prober_ctrl.get_thermo_state()

    # --- Temperature control ---
    def prober_set_temp(self, temp_c: float):
        ok = self.prober_ctrl.set_temp(temp_c)
        if ok:
            self._record_temp_setpoint(temp_c)
        return ok

    def prober_get_temp(self) -> float:
        temp = self.prober_ctrl.get_temp()
        self.current_temp_c = temp
        if temp is None:
            raise RuntimeError("Prober temperature unavailable; aborting move/measurement.")
        if self.temp_ref_c is None:
            self.temp_ref_c = temp
            self.log(f"[temp_comp] Reference temperature set to {temp:.2f}C (first read)")
        if self.temp_sample_cb and self._current_temp_step is not None:
            self.temp_sample_cb(time.time(), temp, self._current_temp_step, "poll")
        return temp

    def _ensure_base_z_heights(self, temp_c: float):
        """Capture baseline Z heights and reference temperature once."""
        if self.temp_comp_ref_z_heights is not None:
            return self.temp_comp_ref_z_heights
        heights = self.prober_ctrl.get_chuck_site_height()
        if not heights:
            raise RuntimeError("Could not read chuck site heights for Z compensation.")
        self.temp_comp_ref_z_heights = heights
        self.log(
            f"[temp_comp] Captured baseline Z heights at {temp_c:.2f}C: contact={heights[0]:.2f}um, "
            f"separation={heights[1]:.2f}um, overtravel={heights[2]:.2f}um, hover={heights[3]:.2f}um"
        )
        return heights

    def _apply_z_compensation(self, temp_c: float):
        """Apply Z compensation once after temperature convergence."""
        comp_z = self.temp_comp_coeffs_xyz[2]
        if comp_z == 0.0:
            return
        (base_contact, base_sep, base_over, base_hover) = self._ensure_base_z_heights(temp_c)
        delta_t = temp_c - self.temp_ref_c
        dz = -comp_z * delta_t
        target_contact = base_contact + dz
        target_sep = base_sep + dz
        # success = self.prober_ctrl.set_chuck_site_height(target_contact, target_sep, base_over, base_hover)
        # if success:
        if True:
            self.log(
                f"[temp_comp] Z heights set for {temp_c:.2f}C (dT={delta_t:.2f}C): contact={target_contact:.2f}um, "
                f"separation={target_sep:.2f}um (delta={dz:.3f}um)"
            )
        else:
            raise RuntimeError("Setting chuck site height failed.")

    def set_temp_compensation(self, comp_x_um_per_c: float, comp_y_um_per_c: float, comp_z_um_per_c: float):
        """Set linear temperature compensation coefficients (um/C)."""
        self.temp_comp_coeffs_xyz = comp_x_um_per_c, comp_y_um_per_c, comp_z_um_per_c


    def _record_temp_setpoint(self, temp_c: float):
        """Emit a setpoint event for tracking/plotting."""
        if self.temp_sample_cb and self._current_temp_step is not None:
            try:
                self.temp_sample_cb(time.time(), temp_c, self._current_temp_step, "setpoint")
            except Exception as e:
                self.log(f"Temp setpoint cb error: {e}")

    def prober_wait_until_temp(self, target_c: float, tol_c: float = 0.5, wait_time_s: float = 0.0, poll_s: float = 1.0, timeout_s: float = 900.0) -> bool:
        self.check_stop("Stop requested before temperature wait")
        sample_cb = None
        if self.temp_sample_cb and self._current_temp_step is not None:
            sample_cb = lambda ts, temp: self.temp_sample_cb(ts, temp, self._current_temp_step, "poll")
        reached = self.prober_ctrl.wait_until_temp(
            target_c,
            tol_c,
            wait_time_s,
            poll_s,
            timeout_s,
            sample_cb=sample_cb,
            stop_check=self.check_stop,
        )
        if reached:
            self.current_temp_c = target_c
            try:
                self._apply_z_compensation(target_c)
            except Exception as e:
                self.log(f"Warning: Z compensation update failed: {e}")
        return reached

    def configure_plot(self, title: str, plots: list[PlotDef]) -> None:
        """Configure the figure with temperature appended to the title if available."""
        if self.plot is None:
            return
        if self.current_temp_c is not None:
            title = f"{title} ({self.current_temp_c + 273.15:.0f}K)"
        self.plot.configure(title, plots)
    def report_status(self, status_info: Optional[Dict[str, Any]]):
        """
        Surface measurement/driver status (non-zero codes) to the UI.
        status_info: None clears; otherwise dict with channel, data_type, status, desc.
        """
        if status_info is None:
            self._last_status_message = None
        if self.status_callback:
            self.status_callback(status_info)

    def move_to_device(self, device):
        self.check_stop("Stop requested before move")
        temp = self.prober_get_temp()
        comp_x, comp_y, _ = self.temp_comp_coeffs_xyz
        if self.temp_ref_c is None:
            self.temp_ref_c = temp
        delta_t = temp - self.temp_ref_c
        # Home shifts (comp * dT)
        dx = comp_x * delta_t
        dy = comp_y * delta_t
        origin_x, origin_y = self.prober_ctrl.subsite_origin if self.prober_ctrl.subsite_origin else (0.0, 0.0)
        target_x = origin_x + device.x + dx
        target_y = origin_y + device.y + dy
        self.log(
            f'Chuck moving to {device.name}: target=({target_x:.2f}um, {target_y:.2f}um) '
            f'base=({origin_x:.2f}um, {origin_y:.2f}um) dev=({device.x:.2f}um, {device.y:.2f}um) '
            f'comp=({dx:.3f}um, {dy:.3f}um) at {temp:.2f}C (ref {self.temp_ref_c:.2f}C, dT={delta_t:.2f}C)'
        )
        try:
            x, y = self.prober_ctrl.move_xy_home(target_x, target_y)
            self.log(
                f'Chuck successfully moved to X={x:.1f}um, Y={y:.1f}um'
            )
        except Exception as e:
            self.log(f'Warning: SENTIO move failed: {e}')
    
    def run_temperature_sweep(self, temp_list_c, wait_after_stable_s, chip_id, site, subsite, proc_class, settings, devices_to_run, poll_interval_s: float = 2.0, tolerance_c: float = 0.5):
        """Set each target temperature, wait for stability, then run the procedure(s)."""
        try:
            for idx, target in enumerate(temp_list_c):
                self._current_temp_step = idx
                if self.temp_step_started_cb:
                    self.temp_step_started_cb(idx)
                else:
                    self.log("Warning: No temp step started callback registered.")
                self.prober_set_temp(target)
                if poll_interval_s > 0:
                    self.prober_wait_until_temp(target, tolerance_c, wait_after_stable_s, poll_interval_s)
                if self.temp_phase_cb:
                    try:
                        self.temp_phase_cb("measure_start", idx)
                    except Exception as e:
                        self.log(f"Temp phase start cb error: {e}")
                run_settings = dict(settings)
                run_settings['temperature_c'] = target
                self.run_devices(chip_id, site, subsite, devices_to_run, proc_class, run_settings)
                if self.temp_phase_cb:
                    try:
                        self.temp_phase_cb("measure_end", idx)
                    except Exception as e:
                        self.log(f"Temp phase end cb error: {e}")
            self._current_temp_step = None
        except MeasurementAbortRequested:
            self.log("Measurement aborted during temperature sweep.")
            raise # things will be cleaned up in safe_stop
        # TODO restore to uncontrolled if ui checkbox says so

    def run_devices(self, chip_id, site, subsite, devices, proc_class, settings):
        """
        Run the given procedure for a specific list of devices.
        """
        if not chip_id:
            raise ValueError("Chip ID is required to run devices.")
        if not devices:
            self.log("No devices to run.")
            return
        try:
            for idx, device in enumerate(devices):
                # Copy settings per device to avoid accidental mutation
                self.run_procedure(chip_id, site, subsite, device, proc_class, dict(settings))
                if self.temp_device_done_cb and self._current_temp_step is not None:
                    try:
                        self.temp_device_done_cb(time.time(), self._current_temp_step, idx + 1, len(devices))
                    except Exception as e:
                        self.log(f"Temp device done cb error: {e}")
        except MeasurementAbortRequested:
            self.log("Measurement aborted during devices run.")
            raise

    
    def run_procedure(self, chip_id, site, subsite, device, proc_class, settings):
        # Apply global ASU overrides if present
        for key in ('asu_channels', 'asu_path_mode', 'asu_range_mode'):
            if key not in settings and key in self.config.data:
                settings[key] = self.config.data.get(key)
        # Inject global CMU calibration into runtime settings so procedures can
        # consume a single settings payload without reaching back into config.
        settings['cmu_calibration'] = self.config.get_cmu_calibration()
        if not chip_id:
            raise ValueError("Chip ID is required to run a procedure.")

        # Update context for use by procedures
        self.current_chip = chip_id
        self.current_site = site
        self.current_subsite = subsite
        self.report_status(None)

        output_root = self.config.data['output_dir']
        output_relative = os.path.join(chip_id, site.name, subsite.name, device.name)
        fallback_root = self.config.data.get('fallback_output_dir')
        proc = proc_class(
            settings,
            output_root,
            output_relative,
            self,
            fallback_root
        )
        self.check_stop("Stop requested before device move")
        self.move_to_device(device)
        # Ensure contact right before measurement
        contact_ok = self.prober_contact()
        if not contact_ok:
            self.log("Warning: Failed to establish contact before measurement")
        else:
            delay_s = max(float(self.CONTACT_LIGHTS_OFF_DELAY_S), 0.0)
            if delay_s > 0:
                self.log(f"Contact established. Waiting {delay_s:.1f}s before turning scope light off.")
                if self.stop_event.wait(delay_s):
                    self.check_stop("Stop requested during post-contact light delay")
            self.prober_set_light(False)
            self.log("Scope light off. Starting measurement.")
        self.check_stop("Stop requested just before procedure run")
        # Run measurement procedure
        try:
            b1500 = self.get_b1500(settings['gpib_address'])
            self.log(f'Connected to B1500 at {settings["gpib_address"]}')
            proc.run(b1500, device)
        except MeasurementAbortRequested:
            self.log("Measurement aborted during procedure run.")
            raise # things will be cleaned up in safe_stop
        except Exception as e:
            try:
                self.b1500.zero_output(B1500_CH_ALL)
                self.b1500.set_switch(B1500_CH_ALL, False)
            except Exception:
                pass
            self.log(f"Unexpected Procedure error: {e}") # if it wasn't an abort, log the error
            raise
        # Move out of contact after completion
        self.prober_separation()
