import os.path
import subprocess
from procedures.base import MeasurementProcedure

class MeasurementRunner:
    def __init__(self, config):
        self.config = config
        self.log_callback = None
        self.plot_start_callback = None
        self.plot_point_callback = None
        self.plot_finalize_callback = None
    
    def log_to_gui(self, msg):
        if self.log_callback:
            self.log_callback(msg)

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
        # Call sentio subsite_move (assume it's a command or API)
        self.log_to_gui(f'Moving to {device.name} at X={device.x}, Y={device.y}')
        # Example: subprocess.run(['sentio', 'subsite_move', str(device.x), str(device.y)])
    
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
        proc.run(device, self)
