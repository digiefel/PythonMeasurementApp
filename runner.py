import os.path
import subprocess
from procedures.base import MeasurementProcedure
from sentio_prober_control.Sentio.ProberSentio import SentioProber
from sentio_prober_control.Sentio.Enumerations import (
    XyReference,
    SteppingContactMode,
    ChuckSite,
)

class MeasurementRunner:
    def __init__(self, config):
        self.config = config
        self.log_callback = None
        self.plot_start_callback = None
        self.plot_point_callback = None
        self.plot_finalize_callback = None
        self.prober = None
        self.subsite_origin = None
    
    def log_to_gui(self, msg):
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
            self.log_to_gui(f'Warning: SENTIO init failed (GPIB0::28::INSTR): {e}')
            self.prober = None
            return False

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
            self.log_to_gui(f'Subsite origin recorded at X={x:.1f}um, Y={y:.1f}um')
        except Exception as e:
            self.log_to_gui(f'Warning: Failed to set subsite origin: {e}')

    # --- Semi-manual prober controls ---
    def prober_go_home(self):
        if not self._ensure_prober():
            return
        try:
            if not self.subsite_origin:
                self.log_to_gui('No subsite origin recorded. Use "Set Home" first.')
                return
            x0, y0 = self.subsite_origin
            x, y = self.prober.move_chuck_xy(XyReference.Home, x0, y0)
            self.prober.wait_all()
            self.log_to_gui(f'Chuck moved to recorded origin X={x:.1f}um, Y={y:.1f}um')
        except Exception as e:
            self.log_to_gui(f'Warning: Go home failed: {e}')

    def prober_set_home(self):
        """Alias for setting subsite/user origin at current position."""
        self.set_subsite_origin()

    def prober_contact(self):
        if not self._ensure_prober():
            return False
        try:
            self.prober.move_chuck_contact()
            self.prober.wait_all()
            self.log_to_gui('Chuck moved to contact')
            return True
        except Exception as e:
            self.log_to_gui(f'Warning: Contact failed: {e}')
            return False

    def prober_separation(self):
        if not self._ensure_prober():
            return False
        try:
            self.prober.move_chuck_separation()
            self.prober.wait_all()
            self.log_to_gui('Chuck moved to separation')
            return True
        except Exception as e:
            self.log_to_gui(f'Warning: Separation failed: {e}')
            return False

    def prober_read_position(self):
        if not self._ensure_prober():
            return None
        try:
            x, y = self.prober.get_chuck_xy(ChuckSite.Wafer, XyReference.Home)
            return x, y
        except Exception as e:
            self.log_to_gui(f'Warning: Read position failed: {e}')
            return None

    def start_live_plot(self, title: str, xlabel: str, ylabel: str, series_label: str = "Data", styles: dict = None, secondary_series: list = None):
        """Notify UI to initialize/clear the live plot."""
        if self.plot_start_callback:
            self.plot_start_callback(title, xlabel, ylabel, series_label, styles or {}, secondary_series or [])

    def add_live_point(self, x, y, series_label: str = "Data"):
        """Send a single data point to the UI plot."""
        if self.plot_point_callback:
            self.plot_point_callback(x, y, series_label)

    def finalize_plot(self, save_path=None):
        """Tell UI to persist the current plot image if requested."""
        if self.plot_finalize_callback:
            self.plot_finalize_callback(save_path)
    
    def move_to_device(self, device):
        self.log_to_gui(f'Moving to {device.name} at X={device.x}, Y={device.y}')
        if not self._ensure_prober():
            return
        try:
            origin_x, origin_y = self.subsite_origin if self.subsite_origin else (0.0, 0.0)
            target_x = origin_x + device.x
            target_y = origin_y + device.y
            x, y = self.prober.move_chuck_xy(XyReference.Home, target_x, target_y)
            self.prober.wait_all()
            # self.prober.move_chuck_contact(ChuckSite.Wafer)
            # self.prober.wait_all(Home
            self.log_to_gui(
                f'Chuck moved to X={x:.1f}um, Y={y:.1f}um '
                f'(origin {"set" if self.subsite_origin else "unset"})'
            )
        except Exception as e:
            self.log_to_gui(f'Warning: SENTIO move failed: {e}')
    
    def run_procedure(self, site, subsite, device, proc_class, settings):
        # Apply global ASU overrides if present
        for key in ('asu_channels', 'asu_path_mode', 'asu_range_mode'):
            if key not in settings and key in self.config.data:
                settings[key] = self.config.data.get(key)

        # Log the ASU settings being applied so the operator can verify them in the GUI log
        if self.log_callback:
            self.log_callback(
                f"ASU settings -> channels: {settings.get('asu_channels', [])}, "
                f"path: {settings.get('asu_path_mode', None)}, "
                f"range: {settings.get('asu_range_mode', None)}"
            )

        proc = proc_class(settings, os.path.join(self.config.data['output_dir'], site.name, subsite.name, device.name))
        self.move_to_device(device)
        # Ensure contact right before measurement
        self.prober_contact()
        # Run measurement procedure
        proc.run(device, self)
        # Move out of contact after completion
        self.prober_separation()

    def run_subsite(self, site, subsite, proc_class, settings, set_home_before_run=False):
        """
        Run the given procedure for every device in the subsite, optionally
        capturing the current chuck position as the subsite origin first.
        """
        if set_home_before_run:
            self.log_to_gui("Setting subsite origin at current chuck position...")
            self.set_subsite_origin()
        for device in subsite.devices:
            # Copy settings per device to avoid accidental mutation
            self.run_procedure(site, subsite, device, proc_class, dict(settings))
