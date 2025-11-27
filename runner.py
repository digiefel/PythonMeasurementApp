import os.path
import subprocess
from procedures.base import MeasurementProcedure

class MeasurementRunner:
    def __init__(self, config):
        self.config = config
        self.log_callback = None
    
    def log_to_gui(self, msg):
        if self.log_callback:
            self.log_callback(msg)
    
    def move_to_device(self, device):
        # Call sentio subsite_move (assume it's a command or API)
        self.log_to_gui(f'Moving to {device.name} at X={device.x}, Y={device.y}')
        # Example: subprocess.run(['sentio', 'subsite_move', str(device.x), str(device.y)])
    
    def run_procedure(self, site, subsite, device, proc_class, settings):
        proc = proc_class(settings, os.path.join(self.config.data['output_dir'], site.name, subsite.name, device.name))
        self.move_to_device(device)
        proc.run(device, self)