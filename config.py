import json
import os
from models import load_devices_csv

class Config:
    def __init__(self, config_path: str, devices_csv_path: str):
        self.config_path = config_path
        self.devices_csv_path = devices_csv_path
        self.data = self.load()
        self.sites = load_devices_csv(devices_csv_path)
    
    def load(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                return json.load(f)
        return {'gpib_address': 'GPIB0::17::INSTR', 'output_dir': 'C:/Users/EMN Lab/Documents/DATA/Davide', 'procedures': {}}
    
    def save(self):
        with open(self.config_path, 'w') as f:
            json.dump(self.data, f, indent=4)
    
    def get_procedure_settings(self, proc_name: str):
        return self.data['procedures'].get(proc_name, {})
    
    def set_procedure_settings(self, proc_name: str, settings: dict):
        self.data['procedures'][proc_name] = settings
        self.save()