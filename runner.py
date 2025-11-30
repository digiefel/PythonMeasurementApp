import os.path
import time
import atexit
from typing import Optional, Dict, Any, Callable
import threading
from procedures.base import MeasurementAbortRequested
from bindings import B1500Session
from sentio_prober_control.Sentio.ProberSentio import SentioProber
from sentio_prober_control.Sentio.Enumerations import (
    XyReference,
    SteppingContactMode,
    ChuckSite,
    ThermoChuckState,
)
from sentio_prober_control.Sentio.Response import Response


class MeasurementRunner:
    def __init__(self, config):
        self.config = config
        self.log_callback = None
        self.plot_start_callback = None
        self.plot_point_callback = None
        self.plot_finalize_callback = None
        self.plot_series_callback = None
        self.status_callback = None
        self._last_status_message = None
        self.b1500: Optional[B1500Session] = None
        self.prober: Optional[SentioProber] = None
        self.subsite_origin = None
        self.current_chip = None
        self.current_site = None
        self.current_subsite = None
        self.current_temp_c: Optional[float] = None
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

    
    def get_prober(self) -> SentioProber:
        """Get or create the SENTIO prober session."""
        if getattr(self, 'prober', None) is None:
            addr = "GPIB0::28::INSTR"
            self.log(f'Opening SENTIO prober session at {addr}')
            self.prober = SentioProber.create_prober("visa", addr)
            self.prober.set_stepping_contact_mode(SteppingContactMode.BackToContact)
        return self.prober

    def set_subsite_origin(self):
        """
        Capture the current chuck position and treat it as the new (0,0) for user-defined moves.
        Operator must have aligned to the reference device before this is called.
        """
        try:
            prober = self.get_prober()
            x, y = prober.get_chuck_xy(ChuckSite.Wafer, XyReference.Home)
            self.subsite_origin = (x, y)
            self.log(f'Subsite origin recorded at X={x:.1f}um, Y={y:.1f}um')
        except Exception as e:
            self.log(f'Warning: Failed to set subsite origin: {e}')

    # --- Semi-manual prober controls ---
    def prober_go_home(self):
        try:
            if not self.subsite_origin:
                self.log('No subsite origin recorded. Use "Set Home" first.')
                return
            prober = self.get_prober()
            x0, y0 = self.subsite_origin
            x, y = prober.move_chuck_xy(XyReference.Home, x0, y0)
            prober.wait_all()
            self.log(f'Chuck moved to recorded origin X={x:.1f}um, Y={y:.1f}um')
        except Exception as e:
            self.log(f'Warning: Go home failed: {e}')

    def prober_set_home(self):
        """Alias for setting subsite/user origin at current position."""
        self.set_subsite_origin()

    def prober_contact(self):
        try:
            prober = self.get_prober()
            prober.move_chuck_contact()
            prober.wait_all()
            self.log('Chuck moved to contact')
            return True
        except Exception as e:
            self.log(f'Warning: Contact failed: {e}')
            return False

    def prober_separation(self):
        try:
            prober = self.get_prober()
            prober.move_chuck_separation()
            prober.wait_all()
            self.log('Chuck moved to separation')
            return True
        except Exception as e:
            self.log(f'Warning: Separation failed: {e}')
            return False

    def prober_read_position(self):
        try:
            prober = self.get_prober()
            x, y = prober.get_chuck_xy(ChuckSite.Wafer, XyReference.Home)
            return x, y
        except Exception as e:
            self.log(f'Warning: Read position failed: {e}')
            return None
    
    def get_temp_setpoint(self) -> Optional[float]:
        try:
            prober = self.get_prober()
            return prober.status.get_chuck_temp_setpoint()
        except Exception as e:
            self.log(f"Warning: Get chuck temperature setpoint failed: {e}")
            return None

    def get_thermo_state(self) -> Optional[str]:
        try:
            prober = self.get_prober()
            state = prober.status.get_chuck_thermo_state()
            match state:
                case ThermoChuckState.Heating:
                    return "heating"
                case ThermoChuckState.Cooling:
                    return "cooling"
                case ThermoChuckState.Controlling:
                    return "controlling"
                case ThermoChuckState.Error:
                    return "error"
                case ThermoChuckState.Soaking:
                    return "soaking"
                case _:
                    return "idle"
        except Exception as e:
            self.log(f"Warning: Get thermo state failed: {e}")
            return None

    def safe_stop(self):
        """
        Universal stop method.
        1. Signals all loops to stop (stop_event).
        2. Aborts and closes B1500 session.
        3. Separates prober.
        4. Returns prober to local.
        """
        self.stop_event.set()
        self.log("Safe stop requested, closing B1500 session.")
        
        b1500 = getattr(self, 'b1500', None)
        if b1500:
            try:
                b1500.abort_measure()
                b1500.zero_output(B1500Session.CH_ALL)
                b1500.set_switch(B1500Session.CH_ALL, False)
                b1500.close()
            except Exception as e:
                self.log(f"Error cleaning up B1500: {e}")
            finally:
                self.b1500 = None
        
        # try to separate
        try:
            self.prober_separation()
        except Exception:
            pass
            
        # return prober to local control
        if self.prober:
            try:
                self.prober.comm.send("*LOCAL")
            except Exception:
                pass

    def should_stop(self) -> bool:
        """Check if a stop has been requested."""
        return self.stop_event.is_set()

    # --- Temperature control ---
    def prober_set_temp(self, temp_c: float):
        self.log(f"Setting temperature setpoint to {temp_c:.2f} C")
        # the set_chuck_temp method is broken, our prober is too old
        # so we just send the command directly
        try:
            prober = self.get_prober()
            prober.status.comm.send(f"status:set_chuck_temp {temp_c:.2f}")
            Response.check_resp(prober.status.comm.read_line())
            self.current_temp_c = temp_c
            return True
        except Exception as e:
            self.log(f"Warning: Set chuck temperature failed: {e}")
            return False

    def prober_get_temp(self) -> Optional[float]:
        try:
            prober = self.get_prober()
            temp = prober.status.get_chuck_temp()
            self.current_temp_c = temp
            return temp
        except Exception as e:
            self.log(f"Warning: Get chuck temperature failed: {e}")
            return None

    def prober_wait_until_temp(self, target_c: float, tol_c: float = 0.5, poll_s: float = 2.0, timeout_s: float = 900.0) -> bool:
        self.log(f"Waiting for chuck to stabilize at {target_c:.1f} C (+/-{tol_c:.1f} C)")
        start = time.time()
        while True:
            if self.should_stop():
                return False
            temp = self.prober_get_temp()
            if temp is not None and abs(temp - target_c) <= tol_c:
                return True
            if timeout_s and (time.time() - start) > timeout_s:
                return False
            time.sleep(max(poll_s, 0.25))

    def start_live_plot(self, title: str, xlabel: str, ylabel: str, series_label: str = "Data", styles: dict = None, secondary_series: list = None, secondary_ylabel: str = None, secondary_yscale: str = None, series_labels: list = None):
        """Notify UI to initialize/clear the live plot."""
        if self.plot_start_callback:
            if self.current_temp_c is not None:
                title = f"{title} ({self.current_temp_c + 273.15:.0f}K)"
            labels = series_labels if series_labels is not None else ([series_label] if series_label else [])
            self.plot_start_callback(title, xlabel, ylabel, series_label, styles or {}, secondary_series or [], secondary_ylabel, secondary_yscale, labels)

    def add_live_point(self, x, y, series_label: str = "Data"):
        """Send a single data point to the UI plot."""
        if self.plot_point_callback:
            self.plot_point_callback(x, y, series_label)

    def add_live_series(self, xs, ys, series_label: str = "Data"):
        """Send a full series to the UI plot in one update."""
        if self.plot_series_callback:
            self.plot_series_callback(xs, ys, series_label)

    def finalize_plot(self, save_path=None):
        """Tell UI to persist the current plot image if requested."""
        if self.plot_finalize_callback:
            self.plot_finalize_callback(save_path)
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
        if self.should_stop():
            return
        self.log(f'Chuck moving to target {device.name} at ΔX={device.x}, ΔY={device.y}')
        try:
            origin_x, origin_y = self.subsite_origin if self.subsite_origin else (0.0, 0.0)
            target_x = origin_x + device.x
            target_y = origin_y + device.y
            prober = self.get_prober()
            x, y = prober.move_chuck_xy(XyReference.Home, target_x, target_y)
            prober.wait_all()
            self.log(
                f'Chuck (absolute) at X={x:.1f}um, Y={y:.1f}um'
            )
        except Exception as e:
            self.log(f'Warning: SENTIO move failed: {e}')
    
    def run_temperature_sweep(self, temp_list_c, wait_after_stable_s, chip_id, site, subsite, device, proc_class, settings, set_home_before_run=False, run_subsite=False, poll_interval_s: float = 2.0, tolerance_c: float = 0.5):
        """Set each target temperature, wait for stability, then run the procedure(s)."""
        first = True
        try:
            for target in temp_list_c:
                if self.should_stop():
                    self.log("Stop requested; aborting temperature sweep.")
                    break
                self.prober_set_temp(target)
                if poll_interval_s > 0:
                    self.prober_wait_until_temp(target, tolerance_c, poll_interval_s)
                if wait_after_stable_s > 0:
                    time.sleep(wait_after_stable_s)
                self.current_temp_c = target
                run_settings = dict(settings)
                run_settings['temperature_c'] = target
                if run_subsite:
                    self.run_subsite(chip_id, site, subsite, proc_class, run_settings, set_home_before_run if first else False)
                else:
                    self.run_procedure(chip_id, site, subsite, device, proc_class, run_settings, set_home_before_run if first else False)
                first = False
        finally:
            self.current_temp_c = None
    
    def run_procedure(self, chip_id, site, subsite, device, proc_class, settings, set_home_before_run=False):
        # Apply global ASU overrides if present
        for key in ('asu_channels', 'asu_path_mode', 'asu_range_mode'):
            if key not in settings and key in self.config.data:
                settings[key] = self.config.data.get(key)
        if not chip_id:
            raise ValueError("Chip ID is required to run a procedure.")

        if set_home_before_run:
            self.log("Setting subsite origin at current chuck position...")
            self.set_subsite_origin()

        # Update context for use by procedures
        self.current_chip = chip_id
        self.current_site = site
        self.current_subsite = subsite
        self.report_status(None)

        proc = proc_class(
            settings,
            os.path.join(self.config.data['output_dir'], chip_id, site.name, subsite.name, device.name),
            self
        )
        self.move_to_device(device)
        # Ensure contact right before measurement
        self.prober_contact()
        # Run measurement procedure
        try:
            proc.run(self.get_b1500(settings['gpib_address']), device)
        except MeasurementAbortRequested:
            # try:
            #     self.b1500.zero_output(B1500Session.CH_ALL)
            #     self.b1500.set_switch(B1500Session.CH_ALL, False)
            # except Exception:
            #     pass
            # self.log("Procedure stopped by user.")
            # things will be cleaned up in safe_stop
            return
        except Exception as e:
            try:
                self.b1500.zero_output(B1500Session.CH_ALL)
                self.b1500.set_switch(B1500Session.CH_ALL, False)
            except Exception:
                pass
            # if it wasn't an abort, log the error
            self.log(f"Procedure error: {e}")
            raise e
        # Move out of contact after completion
        self.prober_separation()

    def run_subsite(self, chip_id, site, subsite, proc_class, settings, set_home_before_run=False):
        """
        Run the given procedure for every device in the subsite, optionally
        capturing the current chuck position as the subsite origin first.
        """
        if not chip_id:
            raise ValueError("Chip ID is required to run a subsite.")
        if set_home_before_run:
            self.log("Setting subsite origin at current chuck position...")
            self.set_subsite_origin()
        for device in subsite.devices:
            # Copy settings per device to avoid accidental mutation
            self.run_procedure(chip_id, site, subsite, device, proc_class, dict(settings))
