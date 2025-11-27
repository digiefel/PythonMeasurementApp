import json
import os
from models import load_devices_csv

DEFAULT_CONFIG = {
    'gpib_address': 'GPIB0::17::INSTR',
    'output_dir': 'C:/Users/EMN Lab/Documents/DATA/Davide',
    # Global ASU configuration (applies to procedures that support it)
    'asu_channels': ["SMU2"],
    'asu_path_mode': 1,
    'asu_range_mode': 0,
    'procedures': {},
    'last_selection': {
        'site': '',
        'subsite': '',
        'device': '',
        'procedure': '',
        'set_home_before_run': True,
        'run_subsite': False,
    },
}


class Config:
    def __init__(self, config_path: str, devices_csv_path: str):
        self.config_path = config_path
        self.devices_csv_path = devices_csv_path
        self.data = self.load()
        self.sites = load_devices_csv(devices_csv_path)
    
    def load(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            # ensure keys exist
            for k, v in DEFAULT_CONFIG.items():
                if k not in data:
                    data[k] = v
            if 'last_selection' not in data:
                data['last_selection'] = DEFAULT_CONFIG['last_selection'].copy()
            return data
        return DEFAULT_CONFIG.copy()
    
    def save(self):
        with open(self.config_path, 'w') as f:
            json.dump(self.data, f, indent=4)
    
    def get_procedure_settings(self, proc_name: str):
        return self.data.get('procedures', {}).get(proc_name, {})
    
    def set_procedure_settings(self, proc_name: str, settings: dict):
        self.data.setdefault('procedures', {})[proc_name] = settings
        self.save()

    def get_last_selection(self):
        return self.data.get('last_selection', DEFAULT_CONFIG['last_selection'])

    def set_last_selection(self, selection: dict):
        """Persist an arbitrary last_selection dictionary."""
        self.data['last_selection'] = selection or {}
        self.save()
