from abc import ABC, abstractmethod
import os
from datetime import datetime


class MeasurementProcedure(ABC):
    def __init__(self, settings: dict, output_dir: str):
        self.settings = settings
        self.output_dir = output_dir
        self._run_timestamp = None
    
    @abstractmethod
    def run(self, device, runner):
        pass
    
    def log(self, message: str, runner):
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_msg = f'[{timestamp}] {message}'
        print(log_msg)
        runner.log_to_gui(log_msg)

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
    
    def save_data(self, data: list, filename: str, headers: list, runner=None, add_timestamp: bool = True):
        os.makedirs(self.output_dir, exist_ok=True)
        path = self.make_output_path(filename, add_timestamp=add_timestamp)
        with open(path, 'w') as f:
            f.write(','.join(headers) + '\n')
            for row in data:
                f.write(','.join(map(str, row)) + '\n')
        self.log(f'Saved data to {path}', runner)

    def format_filename(self, runner, procedure_tag: str, device_name: str):
        """Generate base filename chip_site_subsite_device_timestamp_procedure."""
        chip = getattr(runner, "current_chip", "")
        if not chip:
            raise ValueError("Chip ID is required but not set in runner.")
        site = getattr(runner, "current_site", None)
        subsite = getattr(runner, "current_subsite", None)
        site_name = site.name if site else "site"
        subsite_name = subsite.name if subsite else "subsite"
        timestamp = self.get_run_timestamp()
        return f"{chip}_{site_name}_{subsite_name}_{device_name}_{timestamp}_{procedure_tag}"
