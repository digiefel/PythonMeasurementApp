import os
import tkinter as tk
from tkinter import ttk, filedialog

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

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
        self.runner.plot_start_callback = self.start_plot
        self.runner.plot_point_callback = self.add_plot_point
        self.runner.plot_finalize_callback = self.finish_plot

        self.root.title("Python Measurement App")
        self.root.grid_columnconfigure(2, weight=1)
        self.root.grid_rowconfigure(5, weight=1)
        
        # GUI elements
        self.site_var = tk.StringVar()
        self.subsite_var = tk.StringVar()
        self.device_var = tk.StringVar()
        self.proc_var = tk.StringVar()

        # Matplotlib figure embedded in Tk
        self.fig = Figure(figsize=(5, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.lines = {}
        self.canvas = FigureCanvasTkAgg(self.fig, master=root)
        self.canvas_widget = self.canvas.get_tk_widget()
        
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
        self.log_text.grid(row=5, column=0, columnspan=2, sticky="nsew")

        # Place plot canvas to the right of the controls
        self.canvas_widget.grid(row=0, column=2, rowspan=6, padx=10, pady=5, sticky="nsew")
    
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

    # Live plotting helpers wired via MeasurementRunner callbacks
    def start_plot(self, title, xlabel, ylabel, series_label="Data"):
        self.ax.clear()
        self.ax.set_title(title)
        self.ax.set_xlabel(xlabel)
        self.ax.set_ylabel(ylabel)
        self.ax.grid(True, linestyle="--", alpha=0.4)
        self.lines = {}
        line, = self.ax.plot([], [], label=series_label, color="#1f77b4")
        self.lines[series_label] = {"line": line, "x": [], "y": []}
        self.ax.legend(loc="upper left")
        self.canvas.draw()
        self.root.update_idletasks()

    def add_plot_point(self, x, y, series_label="Data"):
        if series_label not in self.lines:
            line, = self.ax.plot([], [], label=series_label)
            self.lines[series_label] = {"line": line, "x": [], "y": []}
            self.ax.legend(loc="upper left")

        series = self.lines[series_label]
        series["x"].append(x)
        series["y"].append(y)
        series["line"].set_data(series["x"], series["y"])

        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas.draw()
        self.root.update_idletasks()

    def finish_plot(self, save_path=None):
        if save_path:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            self.fig.savefig(save_path, dpi=150, bbox_inches="tight")
            self.log(f'Plot saved to {save_path}')

if __name__ == '__main__':
    root = tk.Tk()
    app = MainUI(root)
    root.mainloop()
