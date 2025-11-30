from abc import ABC, abstractmethod
import os
from datetime import datetime


class MeasurementProcedure(ABC):
    def __init__(self, settings: dict, output_dir: str, runner):
        self.settings = settings
        self.output_dir = output_dir
        self.runner = runner
        self._run_timestamp = None

    @abstractmethod
    def run(self, device):
        pass
    
    def log(self, message: str):
        self.runner.log_to_gui(message)

    # --- Cooperative stop helpers ---
    def stop_requested(self) -> bool:
        return self.runner.should_stop()

    def register_abort_handler(self, handler):
        self.runner.set_abort_handler(handler)

    def clear_abort_handler(self):
        self.runner.set_abort_handler(None)

    def abort_b1500(self, b1500):
        """Abort measurement and reset outputs/switches safely for B1500."""
        try:
            b1500.abort_measure()
        except Exception:
            pass
        try:
            b1500.zero_output(b1500.CH_ALL)
        except Exception:
            pass
        try:
            b1500.set_switch(b1500.CH_ALL, False)
        except Exception:
            pass

    def get_run_timestamp(self):
        if self._run_timestamp is None:
            self._run_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return self._run_timestamp

    def _add_timestamp(self, filename: str):
        """Insert run timestamp before extension to avoid overwrites."""
        stamp = self.get_run_timestamp()
        base, ext = os.path.splitext(filename)
        return f"{base}_{stamp}{ext}"

    def make_output_path(self, filename: str, add_timestamp: bool = True):
        stamped = self._add_timestamp(filename) if add_timestamp else filename
        return os.path.join(self.output_dir, stamped)
    
    def save_data(self, data: list, filename: str, headers: list, add_timestamp: bool = True):
        os.makedirs(self.output_dir, exist_ok=True)
        path = self.make_output_path(filename, add_timestamp=add_timestamp)
        with open(path, 'w') as f:
            f.write(','.join(headers) + '\n')
            for row in data:
                f.write(','.join(map(str, row)) + '\n')
        self.log(f'Saved data to {path}')

    def format_filename(self, procedure_tag: str, device_name: str):
        """Generate base filename chip_site_subsite_device_timestamp_procedure."""
        chip = self.runner.current_chip
        site = self.runner.current_site
        subsite = self.runner.current_subsite
        site_name = site.name
        subsite_name = subsite.name
        timestamp = self.get_run_timestamp()
        return f"{chip}_{site_name}_{subsite_name}_{device_name}_{timestamp}_{procedure_tag}"
