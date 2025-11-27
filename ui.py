import tkinter as tk
from tkinter import ttk, filedialog
from config import Config
from runner import MeasurementRunner
from procedures.rv_sweep import RVSweepProcedure
from procedures.four_terminal_iv_sweep import FourTerminalIVProcedure

class MainUI:
    def __init__(self, root):
        self.root = root
        self.config = Config('global_config.json', 'devices.csv')
        self.runner = MeasurementRunner(self.config)
        self.runner.log_callback = self.log
        
        # GUI elements
        self.site_var = tk.StringVar()
        self.subsite_var = tk.StringVar()
        self.device_var = tk.StringVar()
        self.proc_var = tk.StringVar()
        
        ttk.Label(root, text="Site:").grid(row=0, column=0)
        self.site_cb = ttk.Combobox(root, textvariable=self.site_var, values=[s.name for s in self.config.sites])
        self.site_cb.grid(row=0, column=1)
        self.site_cb.bind('<<ComboboxSelected>>', self.update_subsites)
        
        ttk.Label(root, text="Subsite:").grid(row=1, column=0)
        self.subsite_cb = ttk.Combobox(root, textvariable=self.subsite_var)
        self.subsite_cb.grid(row=1, column=1)
        self.subsite_cb.bind('<<ComboboxSelected>>', self.update_devices)
        
        ttk.Label(root, text="Device:").grid(row=2, column=0)
        self.device_cb = ttk.Combobox(root, textvariable=self.device_var)
        self.device_cb.grid(row=2, column=1)
        
        ttk.Label(root, text="Procedure:").grid(row=3, column=0)
        self.proc_cb = ttk.Combobox(root, textvariable=self.proc_var, values=['RVSweep', 'FourTerminalIV'])
        self.proc_cb.grid(row=3, column=1)
        
        ttk.Button(root, text="Run", command=self.run).grid(row=4, column=0, columnspan=2)
        
        self.log_text = tk.Text(root, height=10)
        self.log_text.grid(row=5, column=0, columnspan=2)
    
    def update_subsites(self, event):
        site = next(s for s in self.config.sites if s.name == self.site_var.get())
        self.subsite_cb['values'] = [sub.name for sub in site.subsites]
    
    def update_devices(self, event):
        site = next(s for s in self.config.sites if s.name == self.site_var.get())
        subsite = next(sub for sub in site.subsites if sub.name == self.subsite_var.get())
        self.device_cb['values'] = [d.name for d in subsite.devices]
    
    def run(self):
        # Get selected items and run
        site = next(s for s in self.config.sites if s.name == self.site_var.get())
        subsite = next(sub for sub in site.subsites if sub.name == self.subsite_var.get())
        device = next(d for d in subsite.devices if d.name == self.device_var.get())
        proc_class = {'RVSweep': RVSweepProcedure, 'FourTerminalIV': FourTerminalIVProcedure}[self.proc_var.get()]
        settings = self.config.get_procedure_settings(self.proc_var.get())
        self.runner.run_procedure(site, subsite, device, proc_class, settings)
    
    def log(self, msg):
        self.log_text.insert(tk.END, msg + '\n')
        self.log_text.see(tk.END)

if __name__ == '__main__':
    root = tk.Tk()
    app = MainUI(root)
    root.mainloop()