from abc import ABC, abstractmethod
import os
import threading
from datetime import datetime

class MeasurementAbortRequested(Exception):
    """Custom exception to indicate measurement abortion."""
    pass

class MeasurementProcedure(ABC):
    SAFE_FALLBACK_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'test_output'))

    def __init__(self, settings: dict, output_root: str, output_relative: str, runner, fallback_root: str | None = None):
        """
        output_root: base directory for primary saves
        output_relative: chip/site/subsite/device relative path
        fallback_root: base directory for fallback saves
        """
        self.settings = settings
        self.output_root = output_root
        self.output_relative = output_relative
        self.fallback_root = fallback_root or self.SAFE_FALLBACK_DIR
        self.runner = runner
        self._run_timestamp = None

    @abstractmethod
    def run(self, b1500, device):
        pass
    
    def log(self, message: str):
        self.runner.log(message)

    def check_stop(self, b1500):
        """Raise an abort if a stop request is active."""
        if not self.runner.stop_event.is_set():
            return
        try:
            b1500.abort_measure()
        except Exception:
            pass
        raise MeasurementAbortRequested("Measurement aborted by user")

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
        return os.path.join(self.output_root, self.output_relative, stamped)
    
    def _write_csv(self, path: str, headers: list, data: list):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(','.join(headers) + '\n')
            for row in data:
                f.write(','.join(map(str, row)) + '\n')

    def _make_fallback_path(self, primary_path: str) -> str:
        """Build a fallback path preserving hierarchy under SAFE_FALLBACK_DIR."""
        fallback_dir = os.path.join(self.fallback_root, self.output_relative)
        return os.path.join(fallback_dir, os.path.basename(primary_path))

    def _threaded_write(self, path: str, headers: list, data: list, result: dict):
        """Write CSV in a thread, storing success/error in result dict."""
        try:
            self._write_csv(path, headers, data)
            result['success'] = True
        except Exception as e:
            result['success'] = False
            result['error'] = e

    def save_data(self, data: list, filename: str, headers: list, add_timestamp: bool = True, primary_timeout: float = 5.0):
        """Persist data to disk with fallback to a safe local directory.
        
        The primary save runs in a separate thread with a timeout to improve robustness
        against slow or unresponsive network paths.
        """
        primary_path = self.make_output_path(filename, add_timestamp=add_timestamp)
        
        # Attempt primary save in a separate thread with timeout
        result = {}
        write_thread = threading.Thread(
            target=self._threaded_write,
            args=(primary_path, headers, data, result),
            daemon=True
        )
        write_thread.start()
        write_thread.join(timeout=primary_timeout)
        
        if write_thread.is_alive():
            # Thread is still running - timed out
            self.log(f"Warning: primary save timed out after {primary_timeout}s; falling back.")
        elif result.get('success'):
            self.log(f'Saved data to {primary_path}')
            return primary_path
        else:
            error = result.get('error', 'Unknown error')
            self.log(f"Warning: primary save path failed ({error}); retrying in fallback directory.")
        
        # Fallback save (run synchronously since fallback should be local/reliable)
        fallback_path = self._make_fallback_path(primary_path)
        try:
            self._write_csv(fallback_path, headers, data)
            # Stick to the fallback directory for subsequent artifacts
            self.output_root = self.fallback_root
            self.log(f"Saved data to fallback path {fallback_path}")
            return fallback_path
        except Exception as e2:
            self.log(f"Error saving to fallback directory: {e2}")
            # Ensure hardware is shut down safely before propagating
            try:
                self.runner.safe_stop()
            finally:
                raise

    def format_filename(self, procedure_tag: str, device_name: str):
        """Generate base filename chip_site_subsite_device_timestamp_procedure."""
        chip = self.runner.current_chip
        site = self.runner.current_site
        subsite = self.runner.current_subsite
        site_name = site.name
        subsite_name = subsite.name
        timestamp = self.get_run_timestamp()
        temp_k = None
        if self.runner.current_temp_c is not None:
            temp_k = self.runner.current_temp_c + 273.15
        base = f"{chip}_{site_name}_{subsite_name}_{device_name}_{timestamp}"
        if temp_k is not None:
            base = f"{base}_{temp_k:.0f}K"
        return f"{base}_{procedure_tag}"
