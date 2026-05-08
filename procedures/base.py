from abc import ABC
from dataclasses import dataclass
import json
import os
import threading
from datetime import datetime
from typing import Any

from instrumentio.constants import SMU_CHANNEL_MAP, WGFMU_CHANNEL_MAP
from instrumentio.bridge import RemoteB1500Session
from runner import MeasurementRunner, MeasurementAbortRequested, MeasurementSkipRequested


@dataclass(frozen=True)
class Choice:
    # Generic dropdown for instrument constants; built-in Python types still cover normal text/number/bool fields.
    options: tuple[tuple[Any, str], ...] = ()
    value_type: type = str

    def coerce(self, value):
        if self.value_type is int:
            return int(float(value))
        if self.value_type is float:
            return float(value)
        return str(value)

    def display_value(self, value):
        value = self.coerce(value)
        return next((label for option_value, label in self.options if option_value == value), self.options[0][1])

    def collect_value(self, ui_value):
        value = next((option_value for option_value, label in self.options if label == ui_value), ui_value)
        return self.coerce(value)


class SMU:
    @staticmethod
    def coerce(value):
        # UI labels like "SMU1" and saved numeric values both become B1500 channel integers.
        return int(float(SMU_CHANNEL_MAP.get(str(value), value)))

    @classmethod
    def display_value(cls, value):
        value = cls.coerce(value)
        return next((label for label, channel in SMU_CHANNEL_MAP.items() if channel == value), next(iter(SMU_CHANNEL_MAP.keys())))

    @classmethod
    def collect_value(cls, ui_value):
        return cls.coerce(SMU_CHANNEL_MAP.get(ui_value, ui_value))


class OptionalSMU:
    @staticmethod
    def coerce(value):
        if value in ("", None) or str(value).strip().lower() in ("none", "off", "disabled"):
            return None
        return SMU.coerce(value)

    @classmethod
    def display_value(cls, value):
        if cls.coerce(value) is None:
            return "None"
        return SMU.display_value(value)

    @classmethod
    def collect_value(cls, ui_value):
        if ui_value == "None":
            return None
        return SMU.collect_value(ui_value)


class WGFMUChannel:
    @staticmethod
    def coerce(value):
        # WGFMU channels use a separate numbering scheme from SMUs, so keep the type distinct.
        return int(float(WGFMU_CHANNEL_MAP.get(str(value), value)))

    @classmethod
    def display_value(cls, value):
        value = cls.coerce(value)
        return next((label for label, channel in WGFMU_CHANNEL_MAP.items() if channel == value), next(iter(WGFMU_CHANNEL_MAP.keys())))

    @classmethod
    def collect_value(cls, ui_value):
        return cls.coerce(WGFMU_CHANNEL_MAP.get(ui_value, ui_value))


@dataclass(frozen=True)
class ProcedureParameter:
    key: str
    label: str
    default: Any = ""
    kind: Any = str
    attr: str | None = None


@dataclass(frozen=True)
class ProcedureAction:
    label: str
    callback: str
    args: tuple = ()
    section: str | None = None
    tooltip: str | None = None


def action(label: str, callback: str, *args, section: str | None = None, tooltip: str | None = None) -> ProcedureAction:
    return ProcedureAction(label=label, callback=callback, args=tuple(args), section=section, tooltip=tooltip)


def parameter(key: str, label: str, default: Any = "", kind: Any = str, attr: str | None = None) -> ProcedureParameter:
    return ProcedureParameter(key=key, label=label, default=default, kind=kind, attr=attr)


class MeasurementProcedure(ABC):
    SAFE_FALLBACK_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'test_output'))
    NAME: str | None = None
    PARAMETERS: tuple[ProcedureParameter, ...] = ()
    UI_ACTIONS: tuple[ProcedureAction, ...] = ()
    CSV_METADATA_ENABLED = True

    def __init__(self, settings: dict, output_root: str, output_relative: str, runner: MeasurementRunner, fallback_root: str | None = None):
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
        self.b1500 = None
        self.wgfmu = None
        self.device = None
        self.asu_channels = []
        self.asu_path_mode = None
        self.asu_range_mode = None
        self._apply_declared_settings()

    @classmethod
    def procedure_name(cls) -> str:
        return cls.NAME or cls.__name__.removesuffix("Procedure")

    @classmethod
    def ui_fields(cls) -> tuple[ProcedureParameter, ...]:
        return cls.PARAMETERS

    @classmethod
    def ui_defaults(cls) -> dict[str, Any]:
        return {param.key: param.default for param in cls.PARAMETERS}

    @classmethod
    def ui_actions(cls) -> tuple[ProcedureAction, ...]:
        return cls.UI_ACTIONS

    def _apply_declared_settings(self):
        """Copy declared procedure parameters from settings onto self.

        New procedures only need to define ``PARAMETERS``. The base class then
        gives them ``self.<key>`` attributes with defaults and light coercion.
        """
        for param in self.PARAMETERS:
            raw_value = self.settings.get(param.key, param.default)
            value = self._coerce_parameter_value(raw_value, param.kind)
            self.settings[param.key] = value
            setattr(self, param.attr or param.key, value)
        # Preserve runner/UI extras so older procedure logic can still use implicit self.<setting> access.
        for key, value in self.settings.items():
            if key == "cmu_calibration" or not isinstance(key, str) or not key.isidentifier():
                continue
            if not hasattr(self, key):
                if key == "asu_channels" and isinstance(value, (list, tuple)):
                    value = [SMU_CHANNEL_MAP.get(str(ch), ch) for ch in value]
                setattr(self, key, value)

    def _coerce_parameter_value(self, value, kind):
        if value is None:
            return None
        # Keep procedure declarations simple: normal Python types for normal fields, custom types for instruments.
        if kind is bool:
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return bool(value)
        if kind is int:
            return int(float(value))
        if kind is float:
            return float(value)
        if kind is str:
            return str(value)
        if kind in (SMU, OptionalSMU, WGFMUChannel):
            return kind.coerce(value)
        if isinstance(kind, Choice):
            return kind.coerce(value)
        raise ValueError(f"Unknown procedure parameter type: {kind!r}")

    def execute(self, b1500: RemoteB1500Session, device):
        """Run the procedure with base-managed instrument handles.

        New procedures should implement ``measure(self, device)`` and use
        ``self.b1500`` / ``self.wgfmu``. Existing procedures with
        ``run(self, b1500, device)`` continue to work.
        """
        self.b1500 = b1500
        self.wgfmu = getattr(b1500, "wgfmu", None)
        self.device = device
        if type(self).measure is not MeasurementProcedure.measure:
            return self.measure(device)
        return self.run(b1500, device)

    def run(self, b1500: RemoteB1500Session, device):
        raise NotImplementedError("Procedure must implement measure(self, device) or run(self, b1500, device).")

    def measure(self, device):
        raise NotImplementedError("Procedure must implement measure(self, device) or run(self, b1500, device).")
    
    def log(self, message: str):
        self.runner.log(message)

    def check_stop(self, b1500: RemoteB1500Session):
        """Check if stop or skip was requested, abort hardware if so, then raise.

        Runs in the worker thread — the only thread that should talk to the
        instrument to avoid GPIB bus contention. ABORT takes priority over SKIP.
        """
        abort = self.runner.stop_event.is_set()
        skip = self.runner.skip_device_event.is_set()
        if not abort and not skip:
            return
        if b1500 is not None:
            try:
                b1500.abort_measure()
            except Exception:
                pass
        if abort:
            raise MeasurementAbortRequested("Measurement aborted by user")
        raise MeasurementSkipRequested("Device skipped by user")

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
    
    def _write_csv(self, path: str, headers: list, data: list, metadata_lines: list[str] | None = None):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            for line in metadata_lines or []:
                f.write(line.rstrip('\n') + '\n')
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
            self._write_csv(path, headers, data, self.csv_metadata_lines())
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
        
        # Attempt primary save in a separate thread so a blocked network path cannot hang the measurement worker.
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
            self._write_csv(fallback_path, headers, data, self.csv_metadata_lines())
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

    def save_plot_png(self, filename: str):
        """Save the current live plot beside the CSV output."""
        plot = getattr(self.runner, "plot", None)
        if plot is None:
            return None
        plot.save_png(filename, self.output_root, self.output_relative, self.fallback_root)
        return self.make_output_path(filename, add_timestamp=False)

    def save_measurement_outputs(
        self,
        data: list,
        procedure_tag: str,
        device,
        headers: list,
        *,
        plot_suffix: str = "_plot.png",
        save_plot: bool = True,
    ):
        """Save the standard CSV plus matching plot PNG for a procedure."""
        base = self.format_filename(procedure_tag, device.name)
        # Most procedures only need this one call: metadata CSV first, then a PNG of the live plot.
        csv_path = self.save_data(data, f"{base}.csv", headers, add_timestamp=False)
        plot_path = None
        if save_plot:
            plot_path = self.save_plot_png(f"{base}{plot_suffix}")
        return csv_path, plot_path

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

    def csv_metadata_lines(self, extra: dict[str, Any] | None = None) -> list[str]:
        if not self.CSV_METADATA_ENABLED:
            return []

        lines = [
            f"# Procedure: {self.procedure_name()}",
            f"# Timestamp: {self.get_run_timestamp()}",
        ]

        if self.device is not None:
            lines.append(f"# Device: {getattr(self.device, 'name', self.device)}")
        if self.runner.current_chip is not None:
            lines.append(f"# Chip: {self.runner.current_chip}")
        if self.runner.current_site is not None:
            lines.append(f"# Site: {self.runner.current_site.name}")
        if self.runner.current_subsite is not None:
            lines.append(f"# Subsite: {self.runner.current_subsite.name}")
        if self.runner.current_temp_c is not None:
            lines.append(f"# Temperature_C: {self.runner.current_temp_c:.6g}")
            lines.append(f"# Temperature_K: {self.runner.current_temp_c + 273.15:.6g}")

        lines.append("# Parameters:")
        seen = set()
        for param in self.PARAMETERS:
            seen.add(param.key)
            # Declared PARAMETERS are saved first in UI order so the CSV header is readable.
            lines.append(f"#   {param.key}: {self._format_metadata_value(self.settings.get(param.key, param.default))}")

        for key in sorted(self.settings):
            if key in seen or key == "cmu_calibration":
                continue
            # Extra runner/config settings are included too, which avoids per-procedure metadata plumbing.
            lines.append(f"#   {key}: {self._format_metadata_value(self.settings[key])}")

        if extra:
            lines.append("# Derived:")
            for key, value in extra.items():
                lines.append(f"#   {key}: {self._format_metadata_value(value)}")

        return lines

    @staticmethod
    def _format_metadata_value(value) -> str:
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, sort_keys=True)
        return str(value)
