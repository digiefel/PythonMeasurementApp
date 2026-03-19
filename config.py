import json
import os
from copy import deepcopy
from typing import Optional
from models import load_devices_csv

DEFAULT_CONFIG = {
    'gpib_address': 'GPIB0::17::INSTR',
    'output_dir': 'C:/Users/EMN Lab/Documents/DATA/Davide',
    'fallback_output_dir': os.path.abspath(os.path.join(os.path.dirname(__file__), 'test_output')),
    # Global ASU configuration (applies to procedures that support it)
    'asu_channels': ["SMU2"],
    'asu_path_mode': 1,
    'asu_range_mode': 0,
    'devices_csv_path': 'TASE_devices.csv',
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
    def __init__(self, config_path: str, devices_csv_path: str = 'TASE_devices.csv'):
        app_root = os.path.dirname(__file__)
        self.config_root = os.path.join(app_root, "saved_configs")
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

    def _merge_defaults(self, data: dict) -> dict:
        merged = deepcopy(DEFAULT_CONFIG)
        merged.update(data or {})
        merged_last = merged.get('last_selection', {})
        default_last = DEFAULT_CONFIG['last_selection']
        normalized_last = deepcopy(default_last)
        normalized_last.update(merged_last)
        if normalized_last.get('temperature_mode') not in ('Setpoint', 'Sweep'):
            normalized_last['temperature_mode'] = 'Setpoint'
        merged['last_selection'] = normalized_last
        if not merged.get('devices_csv_path'):
            merged['devices_csv_path'] = self.default_devices_csv_path
        return merged

    def replace_data(self, data: dict):
        self.data = self._merge_defaults(data)
    
    def load(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            return self._merge_defaults(data)
        return self._merge_defaults({})
    
    def save(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(self.data, f, indent=4)

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
        return self.data.get('cmu_calibration', {}) or {}

    def set_cmu_calibration(self, calibration: dict):
        self.data['cmu_calibration'] = deepcopy(calibration or {})
        self.save()

    def get_last_selection(self):
        return self.data.get('last_selection', DEFAULT_CONFIG['last_selection'])

    def set_last_selection(self, selection: dict):
        """Persist an arbitrary last_selection dictionary."""
        self.data['last_selection'] = selection or {}
        self.save()
