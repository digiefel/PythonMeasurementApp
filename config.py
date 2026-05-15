import json
import os
from copy import deepcopy
from typing import Optional
from instrumentio.constants import DEFAULT_SMU_CHANNEL_MAP
from models import load_devices_csv

DEFAULT_CONFIG = {
    'gpib_address': 'GPIB0::17::INSTR',
    'output_dir': 'output',
    'fallback_output_dir': 'output',
    'b1500': {
        'auto_discover_channels': True,
        'smu_channel_map': deepcopy(DEFAULT_SMU_CHANNEL_MAP),
        'asu_channel_map': {},
        'module_inventory': [],
        'unt_response': '',
    },
    'devices_csv_path': 'devices.csv',
    'cmu_calibration': {},
    'procedures': {},
    'last_selection': {
        'chip_id': '',
        'site': '',
        'subsite': '',
        'device': '',
        'procedure': '',
        'set_home_before_run': True,
        'temperature_enabled': False,
        'temperature_mode': 'Setpoint',
        'temperature_setpoint_c': '',
        'temperature_sweep_c': '',
        'temperature_wait_after_s': 0.0,
        'temp_comp_x_um_per_c': 0.0,
        'temp_comp_y_um_per_c': 0.0,
        'temp_comp_z_um_per_c': 0.0,
    },
}

class Config:
    def __init__(self, config_path: str, devices_csv_path: str = 'devices.csv'):
        self.app_root = os.path.dirname(os.path.abspath(__file__))
        self.config_root = os.path.join(self.app_root, "saved_configs")
        self.config_path = self._resolve_config_path(config_path)
        self.default_devices_csv_path = self._resolve_csv_path(devices_csv_path)
        self.data = self.load()
        configured_csv = self.data.get('devices_csv_path')
        self.devices_csv_path = self._resolve_csv_path(configured_csv or self.default_devices_csv_path)
        self.data['devices_csv_path'] = self.devices_csv_path
        self.sites = []
        self.reload_devices()

    def _resolve_config_path(self, path: str) -> str:
        return path if os.path.isabs(path) else os.path.join(self.config_root, path)

    def _resolve_csv_path(self, path: str) -> str:
        if not path:
            return getattr(self, 'default_devices_csv_path', os.path.join(self.config_root, DEFAULT_CONFIG['devices_csv_path']))
        expanded = os.path.normpath(os.path.expanduser(str(path)))
        if os.path.isabs(expanded):
            return expanded
        saved_cfg_prefix = f"saved_configs{os.sep}"
        alt_prefix = "saved_configs/"
        if expanded.startswith(saved_cfg_prefix) or expanded.startswith(alt_prefix):
            app_root = os.path.dirname(__file__)
            return os.path.normpath(os.path.join(app_root, expanded))
        return os.path.normpath(os.path.join(self.config_root, expanded))

    def _resolve_output_dir(self, path: str) -> str:
        if not path:
            path = DEFAULT_CONFIG['output_dir']
        expanded = os.path.normpath(os.path.expanduser(str(path)))
        if os.path.isabs(expanded):
            return os.path.abspath(expanded)
        return os.path.abspath(os.path.join(self.app_root, expanded))

    def _portable_path(self, path: str, base: str) -> str:
        if not path:
            return path
        try:
            rel = os.path.relpath(os.path.abspath(path), os.path.abspath(base))
        except ValueError:
            return path
        if rel == ".":
            return "."
        if rel.startswith(".." + os.sep) or rel == "..":
            return path
        return rel

    def _serializable_data(self) -> dict:
        data = deepcopy(self.data)
        if data.get('devices_csv_path'):
            data['devices_csv_path'] = self._portable_path(data['devices_csv_path'], self.config_root)
        for key in ('output_dir', 'fallback_output_dir'):
            if data.get(key):
                data[key] = self._portable_path(data[key], self.app_root)
        return data

    def _merge_defaults(self, data: dict) -> dict:
        merged = deepcopy(DEFAULT_CONFIG)
        merged.update(data or {})
        for stale_key in ('asu_enabled', 'asu_channels', 'asu_auto_active_channels', 'asu_path_mode', 'asu_range_mode'):
            merged.pop(stale_key, None)
        merged_last = merged.get('last_selection', {})
        default_last = DEFAULT_CONFIG['last_selection']
        normalized_last = deepcopy(default_last)
        normalized_last.update(merged_last)
        if normalized_last.get('temperature_mode') not in ('Setpoint', 'Sweep'):
            normalized_last['temperature_mode'] = 'Setpoint'
        merged['last_selection'] = normalized_last
        if not merged.get('devices_csv_path'):
            merged['devices_csv_path'] = self.default_devices_csv_path
        b1500_defaults = deepcopy(DEFAULT_CONFIG['b1500'])
        b1500_data = merged.get('b1500', {}) or {}
        if isinstance(b1500_data, dict):
            b1500_defaults.update(b1500_data)
        if not isinstance(b1500_defaults.get('smu_channel_map'), dict) or not b1500_defaults['smu_channel_map']:
            b1500_defaults['smu_channel_map'] = deepcopy(DEFAULT_SMU_CHANNEL_MAP)
        if not isinstance(b1500_defaults.get('module_inventory'), list):
            b1500_defaults['module_inventory'] = []
        if not isinstance(b1500_defaults.get('asu_channel_map'), dict):
            b1500_defaults['asu_channel_map'] = {}
        merged['b1500'] = b1500_defaults
        merged['output_dir'] = self._resolve_output_dir(merged.get('output_dir'))
        merged['fallback_output_dir'] = self._resolve_output_dir(merged.get('fallback_output_dir'))
        return merged

    def replace_data(self, data: dict):
        self.data = self._merge_defaults(data)

    def set_output_dir(self, path: str, persist: bool = False) -> str:
        output_dir = self._resolve_output_dir(path)
        self.data['output_dir'] = output_dir
        if persist:
            self.save()
        return output_dir
    
    def load(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            return self._merge_defaults(data)
        return self._merge_defaults({})
    
    def save(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(self._serializable_data(), f, indent=4)

    def reload_devices(self, csv_path: Optional[str] = None, persist: bool = False):
        target_path = self.devices_csv_path if csv_path is None else self._resolve_csv_path(csv_path)
        sites = load_devices_csv(target_path)
        self.devices_csv_path = target_path
        self.sites = sites
        self.data['devices_csv_path'] = self.devices_csv_path
        if persist:
            self.save()
        return sites
    
    def get_procedure_settings(self, proc_name: str):
        return self.data.get('procedures', {}).get(proc_name, {})
    
    def set_procedure_settings(self, proc_name: str, settings: dict):
        self.data.setdefault('procedures', {})[proc_name] = settings
        self.save()

    def get_cmu_calibration(self) -> dict:
        calib = self.data.get('cmu_calibration', {}) or {}
        if isinstance(calib, dict) and calib:
            return calib

        # Backward compatibility: older files stored CMU calibration under
        # procedures.CVSweep._cmu_calibration.
        legacy = (
            self.data.get('procedures', {})
            .get('CVSweep', {})
            .get('_cmu_calibration', {})
            or {}
        )
        if isinstance(legacy, dict) and legacy:
            self.data['cmu_calibration'] = deepcopy(legacy)
            self.save()
            return self.data['cmu_calibration']

        return {}

    def set_cmu_calibration(self, calibration: dict):
        self.data['cmu_calibration'] = deepcopy(calibration or {})
        self.save()

    def get_last_selection(self):
        return self.data.get('last_selection', DEFAULT_CONFIG['last_selection'])

    def set_last_selection(self, selection: dict):
        """Persist an arbitrary last_selection dictionary."""
        self.data['last_selection'] = selection or {}
        self.save()
