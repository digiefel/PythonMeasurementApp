import os.path
from datetime import datetime
from typing import Optional, Dict, Any, Callable
import threading
from procedures.base import MeasurementProcedure
from sentio_prober_control.Sentio.ProberSentio import SentioProber
from sentio_prober_control.Sentio.Enumerations import (
    XyReference,
    SteppingContactMode,
    ChuckSite,
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
        self.prober = None
        self.subsite_origin = None
        self.current_chip = None
        self.current_site = None
        self.current_subsite = None
        self.stop_event = threading.Event()
        self.abort_handler: Optional[Callable[[], None]] = None
    
    def log(self, msg):
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_msg = f'[{timestamp}] {msg}'
        print(log_msg)
        if self.log_callback:
            self.log_callback(msg)

    def _ensure_prober(self):
        """Lazily create the SENTIO prober session over GPIB (visa address)."""
        if self.prober:
            return True
        try:
            self.prober = SentioProber.create_prober("visa", "GPIB0::28::INSTR")
            self.prober.set_stepping_contact_mode(SteppingContactMode.BackToContact)
            return True
        except Exception as e:
            self.log(f'Warning: SENTIO init failed (GPIB0::28::INSTR): {e}')
            raise e

    def set_subsite_origin(self):
        """
        Capture the current chuck position and treat it as the new (0,0) for user-defined moves.
        Operator must have aligned to the reference device before this is called.
        """
        if not self._ensure_prober():
            return
        try:
            x, y = self.prober.get_chuck_xy(ChuckSite.Wafer, XyReference.Home)
            self.subsite_origin = (x, y)
            self.log(f'Subsite origin recorded at X={x:.1f}um, Y={y:.1f}um')
        except Exception as e:
            self.log(f'Warning: Failed to set subsite origin: {e}')

    # --- Semi-manual prober controls ---
    def prober_go_home(self):
        if not self._ensure_prober():
            return
        try:
            if not self.subsite_origin:
                self.log('No subsite origin recorded. Use "Set Home" first.')
                return
            x0, y0 = self.subsite_origin
            x, y = self.prober.move_chuck_xy(XyReference.Home, x0, y0)
            self.prober.wait_all()
            self.log(f'Chuck moved to recorded origin X={x:.1f}um, Y={y:.1f}um')
        except Exception as e:
            self.log(f'Warning: Go home failed: {e}')

    def prober_set_home(self):
        """Alias for setting subsite/user origin at current position."""
        self.set_subsite_origin()

    def prober_contact(self):
        if not self._ensure_prober():
            return False
        try:
            self.prober.move_chuck_contact()
            self.prober.wait_all()
            self.log('Chuck moved to contact')
            return True
        except Exception as e:
            self.log(f'Warning: Contact failed: {e}')
            return False

    def prober_separation(self):
        if not self._ensure_prober():
            return False
        try:
            self.prober.move_chuck_separation()
            self.prober.wait_all()
            self.log('Chuck moved to separation')
            return True
        except Exception as e:
            self.log(f'Warning: Separation failed: {e}')
            return False

    def prober_read_position(self):
        if not self._ensure_prober():
            return None
        try:
            x, y = self.prober.get_chuck_xy(ChuckSite.Wafer, XyReference.Home)
            return x, y
        except Exception as e:
            self.log(f'Warning: Read position failed: {e}')
            return None
    
    def prober_set_temp(self, temperature_c: float):
        if not self._ensure_prober():
            return False
        try:
            # the set_chuck_temp method is broken, our prober is too old
            # so we just send the command directly
            self.prober.status.comm.send(f"status:set_chuck_temp {temperature_c:.2f}")
            Response.check_resp(self.prober.status.comm.read_line())
            self.log(f'Chuck temperature setpoint set to {temperature_c:.2f}°C (lift_chuck={lift_chuck})')
            return True
        except Exception as e:
            self.log(f'Warning: Set chuck temperature failed: {e}')
            return False
        
    def prober_get_temp(self) -> Optional[float]:
        if not self._ensure_prober():
            return None
        try:
            temp = self.prober.status.get_chuck_temp()
            return temp
        except Exception as e:
            self.log(f'Warning: Get chuck temperature failed: {e}')
            return None

    def start_live_plot(self, title: str, xlabel: str, ylabel: str, series_label: str = "Data", styles: dict = None, secondary_series: list = None, secondary_ylabel: str = None, secondary_yscale: str = None, series_labels: list = None):
        """Notify UI to initialize/clear the live plot."""
        if self.plot_start_callback:
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

    def should_stop(self) -> bool:
        """Check if a stop has been requested."""
        return self.stop_event.is_set()

    def request_stop(self):
        """Request cooperative stop and invoke any registered abort handler."""
        self.stop_event.set()
        if self.abort_handler:
            try:
                self.abort_handler()
            except Exception:
                # Swallow errors from abort to avoid masking stop
                pass

    def clear_stop(self):
        self.stop_event.clear()

    def set_abort_handler(self, handler: Optional[Callable[[], None]]):
        """Register a callable that will be invoked when stop is requested."""
        self.abort_handler = handler
    
    def move_to_device(self, device):
        self.log(f'Moving to {device.name} at X={device.x}, Y={device.y}')
        if not self._ensure_prober():
            return
        try:
            origin_x, origin_y = self.subsite_origin if self.subsite_origin else (0.0, 0.0)
            target_x = origin_x + device.x
            target_y = origin_y + device.y
            x, y = self.prober.move_chuck_xy(XyReference.Home, target_x, target_y)
            self.prober.wait_all()
            self.log(
                f'Chuck moved to X={x:.1f}um, Y={y:.1f}um '
                f'(origin {"set" if self.subsite_origin else "unset"})'
            )
        except Exception as e:
            self.log(f'Warning: SENTIO move failed: {e}')
    
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
        self.clear_stop()
        self.set_abort_handler(None)

        proc = proc_class(
            settings,
            os.path.join(self.config.data['output_dir'], chip_id, site.name, subsite.name, device.name),
            self
        )
        self.move_to_device(device)
        # Ensure contact right before measurement
        self.prober_contact()
        # Run measurement procedure
        proc.run(device)
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
