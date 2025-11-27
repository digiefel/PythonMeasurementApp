import json
import os
import tkinter as tk
from tkinter import ttk, filedialog

import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from config import Config
from runner import MeasurementRunner
from bindings import SMU_CHANNEL_MAP, B1500_VOLTAGE_RANGES, B1500_CURRENT_RANGES
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
        for col, weight in enumerate((1, 1, 2)):
            self.root.grid_columnconfigure(col, weight=weight)
        self.root.grid_rowconfigure(0, weight=3)
        self.root.grid_rowconfigure(1, weight=1)

        # GUI state
        self.site_var = tk.StringVar()
        self.subsite_var = tk.StringVar()
        self.device_var = tk.StringVar()
        self.proc_var = tk.StringVar()
        self.param_vars = {}

        # Procedure field definitions (label, type)
        self.procedure_fields = {
            'RVSweep': [
                ('rv_start', 'RV Start (V)', float),
                ('rv_stop', 'RV Stop (V)', float),
                ('rv_step', 'RV Step (V)', float),
                ('pulse_length', 'Pulse Length (s)', float),
                ('read_bias', 'Read Bias (V)', float),
                ('set_amplitude', 'Set Amplitude (V)', float),
                ('mock_mode', 'Mock Mode', bool),
            ],
            'FourTerminalIV': [
                ('gpib_address', 'GPIB Address', str),
                ('force_high_channel', 'Force High SMU', 'smu'),
                ('force_low_channel', 'Force Low SMU', 'smu'),
                ('sense_high_channel', 'Sense High SMU', 'smu'),
                ('sense_low_channel', 'Sense Low SMU', 'smu'),
                ('force_current_range', 'Force Current Range', 'current_range'),
                ('start_current', 'Start Current (A)', float),
                ('stop_current', 'Stop Current (A)', float),
                ('points', 'Points', int),
                ('voltage_compliance', 'Voltage Compliance (V)', float),
                ('power_compliance', 'Power Compliance (W)', float),
                ('measurement_range', 'Voltage Measurement Range', 'voltage_range'),
                ('current_compliance', 'Return Current Compliance (A)', float),
                ('hold_time', 'Hold Time (s)', float),
                ('delay_time', 'Delay Time (s)', float),
                ('second_delay', 'Second Delay (s)', float),
            ],
        }
        self.procedure_defaults = {
            'RVSweep': {
                'rv_start': 0.1,
                'rv_stop': 2.0,
                'rv_step': 0.1,
                'pulse_length': 100e-6,
                'read_bias': 0.3,
                'set_amplitude': -1.8,
                'mock_mode': True,
            },
            'FourTerminalIV': {
                'gpib_address': 'GPIB0::17::INSTR',
                'force_high_channel': 4,
                'force_low_channel': 3,
                'sense_high_channel': 5,
                'sense_low_channel': 6,
                'force_current_range': 0.0,
                'start_current': 0.0,
                'stop_current': 1e-6,
                'points': 75,
                'voltage_compliance': 10.0,
                'power_compliance': 0.0,
                'measurement_range': 0.0,
                'current_compliance': 0.01,
                'hold_time': 0.0,
                'delay_time': 0.0,
                'second_delay': 0.0,
            },
        }

        self.build_layout()
        self.populate_sites()
        # Default to first procedure in list
        default_proc = next(iter(self.procedure_fields.keys()))
        last_sel = self.config.get_last_selection()
        proc_to_use = last_sel.get('procedure') or default_proc
        self.proc_var.set(proc_to_use)
        self.proc_cb.set(proc_to_use)
        self.render_param_form(proc_to_use)
        self.apply_last_selection(last_sel)

    def build_layout(self):
        # Selection section
        self.selection_frame = ttk.LabelFrame(self.root, text="Selection")
        self.selection_frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        for col in range(2):
            self.selection_frame.grid_columnconfigure(col, weight=1)

        ttk.Label(self.selection_frame, text="Site").grid(row=0, column=0, sticky="w")
        self.site_cb = ttk.Combobox(self.selection_frame, textvariable=self.site_var, values=[s.name for s in self.config.sites])
        self.site_cb.grid(row=0, column=1, sticky="ew", pady=2)
        self.site_cb.bind('<<ComboboxSelected>>', self.update_subsites)

        ttk.Label(self.selection_frame, text="Subsite").grid(row=1, column=0, sticky="w")
        self.subsite_cb = ttk.Combobox(self.selection_frame, textvariable=self.subsite_var)
        self.subsite_cb.grid(row=1, column=1, sticky="ew", pady=2)
        self.subsite_cb.bind('<<ComboboxSelected>>', self.update_devices)

        ttk.Label(self.selection_frame, text="Device").grid(row=2, column=0, sticky="w")
        self.device_cb = ttk.Combobox(self.selection_frame, textvariable=self.device_var)
        self.device_cb.grid(row=2, column=1, sticky="ew", pady=2)

        ttk.Label(self.selection_frame, text="Procedure").grid(row=3, column=0, sticky="w")
        self.proc_cb = ttk.Combobox(self.selection_frame, textvariable=self.proc_var, values=list(self.procedure_fields.keys()))
        self.proc_cb.grid(row=3, column=1, sticky="ew", pady=2)
        self.proc_cb.bind('<<ComboboxSelected>>', self.on_proc_change)

        # Action buttons
        action_frame = ttk.Frame(self.selection_frame)
        action_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=6)
        action_frame.grid_columnconfigure(0, weight=1)
        action_frame.grid_columnconfigure(1, weight=1)
        ttk.Button(action_frame, text="Load Settings", command=self.load_settings).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(action_frame, text="Save Settings", command=self.save_settings).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        ttk.Button(self.selection_frame, text="Run", command=self.run).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        # Procedure settings section
        self.params_frame = ttk.LabelFrame(self.root, text="Procedure Settings")
        self.params_frame.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        self.params_frame.grid_columnconfigure(0, weight=1)
        self.params_frame.grid_columnconfigure(1, weight=1)

        # Matplotlib figure embedded in Tk
        self.fig = Figure(figsize=(5, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.lines = {}
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.grid(row=0, column=2, rowspan=1, padx=8, pady=8, sticky="nsew")

        # Log section
        log_frame = ttk.LabelFrame(self.root, text="Log")
        log_frame.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=8, pady=8)
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, height=10, wrap="word")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll.grid(row=0, column=1, sticky="ns")

    def populate_sites(self):
        if self.config.sites:
            self.site_var.set(self.config.sites[0].name)
            self.update_subsites()

    def update_subsites(self, event=None):
        site = next((s for s in self.config.sites if s.name == self.site_var.get()), None)
        if not site:
            return
        self.subsite_cb['values'] = [sub.name for sub in site.subsites]
        if site.subsites:
            self.subsite_var.set(site.subsites[0].name)
            self.update_devices()

    def update_devices(self, event=None):
        site = next((s for s in self.config.sites if s.name == self.site_var.get()), None)
        subsite = next((sub for sub in site.subsites if sub.name == self.subsite_var.get()), None) if site else None
        if not subsite:
            self.device_cb['values'] = []
            return
        self.device_cb['values'] = [d.name for d in subsite.devices]
        if subsite.devices:
            self.device_var.set(subsite.devices[0].name)

    def on_proc_change(self, event=None):
        self.render_param_form(self.proc_var.get())

    def render_param_form(self, proc_name):
        # Clear previous widgets
        for child in self.params_frame.winfo_children():
            child.destroy()
        self.param_vars = {}

        fields = self.procedure_fields.get(proc_name, [])
        if not fields:
            ttk.Label(self.params_frame, text="Select a procedure to edit settings.").grid(row=0, column=0, sticky="w", padx=4, pady=4)
            return

        settings = self.config.get_procedure_settings(proc_name)
        for idx, (key, label, cast) in enumerate(fields):
            ttk.Label(self.params_frame, text=label).grid(row=idx, column=0, sticky="w", padx=4, pady=2)
            default_val = self.procedure_defaults.get(proc_name, {}).get(key, "")
            val = settings.get(key, default_val)
            if cast is bool:
                var = tk.BooleanVar(value=bool(val))
                chk = ttk.Checkbutton(self.params_frame, variable=var)
                chk.grid(row=idx, column=1, sticky="w", padx=4, pady=2)
                self.param_vars[key] = (var, cast)
            elif cast == 'smu':
                label_val = self.lookup_smu_label(val)
                var = tk.StringVar(value=label_val)
                combo = ttk.Combobox(self.params_frame, textvariable=var, values=list(SMU_CHANNEL_MAP.keys()), state="readonly")
                combo.grid(row=idx, column=1, sticky="ew", padx=4, pady=2)
                self.param_vars[key] = (var, cast)
            elif cast == 'voltage_range':
                label_val = self.lookup_range_label(val, B1500_VOLTAGE_RANGES)
                var = tk.StringVar(value=label_val)
                combo = ttk.Combobox(self.params_frame, textvariable=var, values=[label for _, label in B1500_VOLTAGE_RANGES], state="readonly")
                combo.grid(row=idx, column=1, sticky="ew", padx=4, pady=2)
                self.param_vars[key] = (var, cast)
            elif cast == 'current_range':
                label_val = self.lookup_range_label(val, B1500_CURRENT_RANGES)
                var = tk.StringVar(value=label_val)
                combo = ttk.Combobox(self.params_frame, textvariable=var, values=[label for _, label in B1500_CURRENT_RANGES], state="readonly")
                combo.grid(row=idx, column=1, sticky="ew", padx=4, pady=2)
                self.param_vars[key] = (var, cast)
            else:
                var = tk.StringVar(value=str(val))
                entry = ttk.Entry(self.params_frame, textvariable=var)
                entry.grid(row=idx, column=1, sticky="ew", padx=4, pady=2)
                self.params_frame.grid_columnconfigure(1, weight=1)
                self.param_vars[key] = (var, cast)

    def collect_settings(self):
        proc_name = self.proc_var.get()
        fields = self.procedure_fields.get(proc_name, [])
        settings = {}
        for key, _, cast in fields:
            var, _ = self.param_vars.get(key, (None, cast))
            if var is None:
                continue
            try:
                if cast is bool:
                    settings[key] = bool(var.get())
                elif cast == 'smu':
                    settings[key] = SMU_CHANNEL_MAP.get(var.get(), var.get())
                elif cast == 'voltage_range':
                    settings[key] = self.lookup_range_value(var.get(), B1500_VOLTAGE_RANGES)
                elif cast == 'current_range':
                    settings[key] = self.lookup_range_value(var.get(), B1500_CURRENT_RANGES)
                elif cast is int:
                    settings[key] = int(float(var.get()))
                elif cast is float:
                    settings[key] = float(var.get())
                else:
                    settings[key] = var.get()
            except ValueError:
                # Leave invalid entries as strings to avoid hard fail; they will be validated by procedure
                settings[key] = var.get()
        return settings

    def load_settings(self):
        proc_name = self.proc_var.get()
        if not proc_name:
            self.log("Select a procedure before loading settings.")
            return
        path = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Load settings"
        )
        if not path:
            return
        try:
            with open(path, 'r') as f:
                self.config.data = json.load(f)
                self.config.config_path = path
        except Exception as e:
            self.log(f'Failed to load settings: {e}')
            return
        self.render_param_form(proc_name)
        self.apply_last_selection(self.config.get_last_selection())
        self.log(f'Loaded settings from {path}')

    def save_settings(self):
        proc_name = self.proc_var.get()
        if not proc_name:
            self.log("Select a procedure before saving settings.")
            return
        settings = self.collect_settings()
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            initialfile=os.path.basename(self.config.config_path),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Save settings as"
        )
        if not path:
            return
        self.config.config_path = path
        # Update config in memory before saving
        self.config.set_procedure_settings(proc_name, settings)
        self.config.set_last_selection(
            self.site_var.get(),
            self.subsite_var.get(),
            self.device_var.get(),
            proc_name
        )
        self.log(f'Saved settings to {path}')

    def run(self):
        proc_name = self.proc_var.get()
        if not proc_name:
            self.log("Select a procedure before running.")
            return
        site = next((s for s in self.config.sites if s.name == self.site_var.get()), None)
        subsite = next((sub for sub in site.subsites if sub.name == self.subsite_var.get()), None) if site else None
        device = next((d for d in subsite.devices if d.name == self.device_var.get()), None) if subsite else None
        if not all([site, subsite, device]):
            self.log("Select site, subsite, and device before running.")
            return

        proc_class = {'RVSweep': RVSweepProcedure, 'FourTerminalIV': FourTerminalIVProcedure}[proc_name]
        settings = self.collect_settings()
        # Persist the settings as part of the run so they are available next time
        self.config.set_procedure_settings(proc_name, settings)
        # Persist last selection
        self.config.set_last_selection(
            self.site_var.get(),
            self.subsite_var.get(),
            self.device_var.get(),
            proc_name
        )
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

    # Helpers
    def lookup_smu_label(self, value):
        # Accept already a label, or map numeric back to label
        if value in SMU_CHANNEL_MAP:
            return value
        for label, ch in SMU_CHANNEL_MAP.items():
            if str(ch) == str(value):
                return label
        return next(iter(SMU_CHANNEL_MAP.keys()))

    def lookup_range_label(self, numeric_value, options):
        for val, label in options:
            if float(numeric_value) == float(val):
                return label
        return options[0][1] if options else ""

    def lookup_range_value(self, label, options):
        for val, lbl in options:
            if lbl == label:
                return val
        return options[0][0] if options else 0.0

    def apply_last_selection(self, last_sel):
        if last_sel.get('procedure'):
            self.proc_var.set(last_sel['procedure'])
            self.proc_cb.set(last_sel['procedure'])
            self.render_param_form(last_sel['procedure'])
        if last_sel.get('site'):
            self.site_var.set(last_sel['site'])
            self.update_subsites()
        if last_sel.get('subsite'):
            self.subsite_var.set(last_sel['subsite'])
            self.update_devices()
        if last_sel.get('device'):
            self.device_var.set(last_sel['device'])


if __name__ == '__main__':
    root = tk.Tk()
    app = MainUI(root)
    root.mainloop()
