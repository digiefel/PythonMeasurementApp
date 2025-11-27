from abc import ABC, abstractmethod
import os
from datetime import datetime

class MeasurementProcedure(ABC):
    def __init__(self, settings: dict, output_dir: str):
        self.settings = settings
        self.output_dir = output_dir
    
    @abstractmethod
    def run(self, device, runner):
        pass
    
    def log(self, message: str, runner):
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_msg = f'[{timestamp}] {message}'
        print(log_msg)
        runner.log_to_gui(log_msg)
    
    def save_data(self, data: list, filename: str, headers: list, runner=None):
        os.makedirs(self.output_dir, exist_ok=True)
        path = os.path.join(self.output_dir, filename)
        with open(path, 'w') as f:
            f.write(','.join(headers) + '\n')
            for row in data:
                f.write(','.join(map(str, row)) + '\n')
        self.log(f'Saved data to {path}', runner)