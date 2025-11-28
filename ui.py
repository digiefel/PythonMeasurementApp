import json
import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog
from tkinter import messagebox
from typing import Optional

from config import Config
from runner import MeasurementRunner
from bindings import SMU_CHANNEL_MAP, B1500_VOLTAGE_RANGES, B1500_CURRENT_RANGES, B1500Session
from procedures.rv_sweep import RVSweepProcedure
from procedures.four_terminal_iv_sweep import FourTerminalIVProcedure
from procedures.oxide_breakdown import OxideBreakdownProcedure
from tooltip_helper import attach_tooltip
from plot_manager import PlotManager, PlotSpec


class MainUI:
    def __init__(self, root):
        self.root = root
        self.config = Config('global_config.json', 'devices.csv')
        self.runner = MeasurementRunner(self.config)
        self.runner.log_callback = self._post_log
        self.runner.plot_start_callback = self._post_plot_start
        self.runner.plot_point_callback = self._post_plot_point
        self.runner.plot_series_callback = self._post_plot_series
        self.runner.plot_finalize_callback = self._post_plot_finish
        self.runner.status_callback = self._post_status
        self._run_thread = None
        # Styles for Run/Stop
        style = ttk.Style()
        style.configure("Run.TButton", foreground="green")
        style.configure("Stop.TButton", foreground="red")

        self.root.title("Python Measurement App")
        for col, weight in enumerate((1, 1, 2)):
            self.root.grid_columnconfigure(col, weight=weight)
        self.root.grid_rowconfigure(0, weight=3)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(2, weight=2)

        # GUI state
        self.site_var = tk.StringVar()
        self.subsite_var = tk.StringVar()
        self.device_var = tk.StringVar()
        self.proc_var = tk.StringVar()
        self.param_vars = {}
        # Global ASU state
        self.asu_channels_var = tk.StringVar()
        self.asu_path_var = tk.StringVar()
        self.asu_range_var = tk.BooleanVar()
        self.status_labels = {}
        # Run options
        self.run_subsite_var = tk.BooleanVar(value=False)
        self.set_home_var = tk.BooleanVar(value=False)
        self.prober_contact_state = tk.BooleanVar(value=False)
        self.position_var = tk.StringVar(value="X=-- , Y=--")
        self.chip_var = tk.StringVar()

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
            'OxideBreakdown': [
                ('gpib_address', 'GPIB Address', str),
                ('high_channel', 'High SMU', 'smu'),
                ('low_channel', 'Low SMU', 'smu'),
                ('v_max', 'Vmax (V)', float),
                ('points', 'Points', int),
                ('double_sweep', 'Double Sweep (return)', bool),
                ('current_compliance', 'Current Compliance (A)', float),
                ('current_range', 'Current Range (A)', 'current_range'),
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
            'OxideBreakdown': {
                'gpib_address': 'GPIB0::17::INSTR',
                'high_channel': 4,
                'low_channel': 3,
                'v_max': 15.0,
                'points': 75,
                'double_sweep': True,
                'current_compliance': 1e-3,
                'current_range': 0.0,
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
        self.load_global_asu()

    def build_layout(self):
        # Selection section
        self.selection_frame = ttk.LabelFrame(self.root, text="Selection")
        self.selection_frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        for col in range(2):
            self.selection_frame.grid_columnconfigure(col, weight=1)

        ttk.Label(self.selection_frame, text="Chip ID", font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Entry(self.selection_frame, textvariable=self.chip_var).grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(self.selection_frame, text="Site").grid(row=1, column=0, sticky="w")
        self.site_cb = ttk.Combobox(self.selection_frame, textvariable=self.site_var, values=[s.name for s in self.config.sites])
        self.site_cb.grid(row=1, column=1, sticky="ew", pady=2)
        self.site_cb.bind('<<ComboboxSelected>>', self.update_subsites)

        ttk.Label(self.selection_frame, text="Subsite").grid(row=2, column=0, sticky="w")
        self.subsite_cb = ttk.Combobox(self.selection_frame, textvariable=self.subsite_var)
        self.subsite_cb.grid(row=2, column=1, sticky="ew", pady=2)
        self.subsite_cb.bind('<<ComboboxSelected>>', self.update_devices)

        ttk.Label(self.selection_frame, text="Device").grid(row=3, column=0, sticky="w")
        self.device_cb = ttk.Combobox(self.selection_frame, textvariable=self.device_var)
        self.device_cb.grid(row=3, column=1, sticky="ew", pady=2)

        ttk.Label(self.selection_frame, text="Procedure").grid(row=4, column=0, sticky="w")
        self.proc_cb = ttk.Combobox(self.selection_frame, textvariable=self.proc_var, values=list(self.procedure_fields.keys()))
        self.proc_cb.grid(row=4, column=1, sticky="ew", pady=2)
        self.proc_cb.bind('<<ComboboxSelected>>', self.on_proc_change)

        # Global ASU config
        ttk.Label(self.selection_frame, text="ASU Channels (comma)").grid(row=5, column=0, sticky="w")
        self.asu_channels_entry = ttk.Entry(self.selection_frame, textvariable=self.asu_channels_var)
        self.asu_channels_entry.grid(row=5, column=1, sticky="ew", pady=2)

        ttk.Label(self.selection_frame, text="ASU Path Mode").grid(row=6, column=0, sticky="w")
        self.asu_path_entry = ttk.Entry(self.selection_frame, textvariable=self.asu_path_var)
        self.asu_path_entry.grid(row=6, column=1, sticky="ew", pady=2)

        ttk.Label(self.selection_frame, text="ASU 1pA Range Enable").grid(row=7, column=0, sticky="w")
        self.asu_range_check = ttk.Checkbutton(self.selection_frame, variable=self.asu_range_var)
        self.asu_range_check.grid(row=7, column=1, sticky="w", pady=2)

        ttk.Checkbutton(self.selection_frame, text="Run all devices in subsite", variable=self.run_subsite_var).grid(row=8, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Checkbutton(self.selection_frame, text="Set subsite origin at start", variable=self.set_home_var).grid(row=9, column=0, columnspan=2, sticky="w")

        # Action buttons
        action_frame = ttk.Frame(self.selection_frame)
        action_frame.grid(row=10, column=0, columnspan=2, sticky="ew", pady=6)
        action_frame.grid_columnconfigure(0, weight=1)
        action_frame.grid_columnconfigure(1, weight=1)
        ttk.Button(action_frame, text="Load Settings", command=self.load_settings).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(action_frame, text="Save Settings", command=self.save_settings).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self.run_button = ttk.Button(self.selection_frame, text="Run", command=self.run, style="Run.TButton")
        self.run_button.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        # Procedure settings section
        self.params_frame = ttk.LabelFrame(self.root, text="Procedure Settings")
        self.params_frame.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        self.params_frame.grid_columnconfigure(0, weight=1)
        self.params_frame.grid_columnconfigure(1, weight=1)

        # Matplotlib figure embedded in Tk (managed by PlotManager)
        self.plot = PlotManager(self.root)
        self.canvas_widget = self.plot.canvas_widget
        self.canvas_widget.grid(row=0, column=2, rowspan=1, padx=8, pady=8, sticky="nsew")

        # Prober controls (bottom left)
        prober_frame = ttk.LabelFrame(self.root, text="Prober Control")
        prober_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        for c in range(2):
            prober_frame.grid_columnconfigure(c, weight=1)
        ttk.Button(prober_frame, text="Go Home", command=self.prober_go_home).grid(row=0, column=0, sticky="ew", padx=4, pady=2)
        ttk.Button(prober_frame, text="Set Home", command=self.prober_set_home).grid(row=0, column=1, sticky="ew", padx=4, pady=2)
        ttk.Button(prober_frame, text="Go To Device", command=self.prober_go_to_device).grid(row=1, column=0, columnspan=2, sticky="ew", padx=4, pady=2)
        self.contact_button = ttk.Button(prober_frame, text="Contact", command=self.toggle_contact)
        self.contact_button.grid(row=2, column=0, columnspan=2, sticky="ew", padx=4, pady=2)
        ttk.Button(prober_frame, text="Read Position", command=self.read_position).grid(row=3, column=0, sticky="ew", padx=4, pady=2)
        ttk.Label(prober_frame, textvariable=self.position_var).grid(row=3, column=1, sticky="w", padx=4, pady=2)

        # Log section (bottom right)
        log_frame = ttk.LabelFrame(self.root, text="Log")
        log_frame.grid(row=1, column=1, columnspan=2, sticky="nsew", padx=8, pady=8)
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, height=10, wrap="word")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.status_frame = ttk.Frame(log_frame)
        self.status_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.status_labels = {}
        self._render_status_ok()

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
        # Refresh ASU globals and UI fields
        self.load_global_asu()
        self.render_param_form(proc_name)
        self.apply_last_selection(self.config.get_last_selection())
        self.log(f'Loaded settings from {path}')

    def save_settings(self):
        proc_name = self.proc_var.get()
        if not proc_name:
            self.log("Select a procedure before saving settings.")
            return
        self.update_global_asu_from_ui()
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
        # Global ASU settings are already merged into config.data by update_global_asu_from_ui
        self.config.set_procedure_settings(proc_name, settings)
        self.config.set_last_selection(self.build_last_selection())
        self.log(f'Saved settings to {path}')

    def run(self):
        proc_name = self.proc_var.get()
        if not proc_name:
            self.log("Select a procedure before running.")
            return
        self.update_global_asu_from_ui()
        chip_id = self.chip_var.get().strip()
        if not chip_id:
            tk.messagebox.showerror("Missing Chip ID", "Please enter a Chip ID before running.")
            return
        site = next((s for s in self.config.sites if s.name == self.site_var.get()), None)
        subsite = next((sub for sub in site.subsites if sub.name == self.subsite_var.get()), None) if site else None
        device = next((d for d in subsite.devices if d.name == self.device_var.get()), None) if subsite else None
        if not all([site, subsite, device]):
            self.log("Select site, subsite, and device before running.")
            return

        proc_class = {
            'RVSweep': RVSweepProcedure,
            'FourTerminalIV': FourTerminalIVProcedure,
            'OxideBreakdown': OxideBreakdownProcedure,
        }[proc_name]
        settings = self.collect_settings()
        # Cache current settings/selection in memory only to avoid overwriting config files on run
        self.config.data.setdefault('procedures', {})[proc_name] = settings
        self.config.data['last_selection'] = self.build_last_selection()
        run_all = self.run_subsite_var.get()
        set_home = self.set_home_var.get()
        if self._run_thread and self._run_thread.is_alive():
            self.log("A run is already in progress.")
            return
        def target():
            try:
                if run_all:
                    self._post_log("Running entire subsite; align to reference device before start.")
                    self.runner.run_subsite(chip_id, site, subsite, proc_class, settings, set_home)
                else:
                    self.runner.run_procedure(chip_id, site, subsite, device, proc_class, settings, set_home)
            except Exception as e:
                self._post_log(f'Run error: {e}')
            finally:
                self._post(lambda: None)  # ensure main loop wakes
                self._run_thread = None
                self._post(self._set_running_state, False)
        self._set_running_state(True)
        self._run_thread = threading.Thread(target=target, daemon=True)
        self._run_thread.start()

    def stop_run(self):
        """Triggered by Stop button to abort measurement safely."""
        self.runner.request_stop()
        self.log("Stop requested.")
        self._set_running_state(True)  # keep button as Stop until thread exits

    # --- Prober control handlers ---
    def prober_go_home(self):
        self.runner.prober_go_home()

    def prober_set_home(self):
        self.runner.prober_set_home()

    def prober_go_to_device(self):
        site = next((s for s in self.config.sites if s.name == self.site_var.get()), None)
        subsite = next((sub for sub in site.subsites if sub.name == self.subsite_var.get()), None) if site else None
        device = next((d for d in subsite.devices if d.name == self.device_var.get()), None) if subsite else None
        if not all([site, subsite, device]):
            self.log("Select site, subsite, and device before moving.")
            return
        self.runner.move_to_device(device)

    def toggle_contact(self):
        target_contact = not self.prober_contact_state.get()
        ok = self.runner.prober_contact() if target_contact else self.runner.prober_separation()
        if ok:
            self.prober_contact_state.set(target_contact)
            self.contact_button.config(text="Separation" if target_contact else "Contact")

    def prober_separation(self):
        ok = self.runner.prober_separation()
        if ok:
            self.prober_contact_state.set(False)
            self.contact_button.config(text="Contact")

    def read_position(self):
        pos = self.runner.prober_read_position()
        if pos:
            x, y = pos
            self.position_var.set(f"X={x:.1f}um , Y={y:.1f}um")
        else:
            self.position_var.set("X=-- , Y=--")
    
    def log(self, msg):
        self.log_text.insert(tk.END, msg + '\n')
        self.log_text.see(tk.END)

    def _post(self, fn, *args):
        self.root.after(0, lambda: fn(*args))

    def _post_log(self, msg):
        self._post(self.log, msg)

    def _post_status(self, info: Optional[dict]):
        self._post(self.show_status, info)

    def _post_plot_start(self, *args, **kwargs):
        self._post(self.start_plot, *args, **kwargs)

    def _post_plot_point(self, *args, **kwargs):
        self._post(self.add_plot_point, *args, **kwargs)

    def _post_plot_series(self, *args, **kwargs):
        self._post(self.add_plot_series, *args, **kwargs)

    def _post_plot_finish(self, *args, **kwargs):
        self._post(self.finish_plot, *args, **kwargs)

    def _set_running_state(self, running: bool):
        """Toggle Run/Stop button appearance and command."""
        if running:
            self.run_button.config(text="Stop", command=self.stop_run, style="Stop.TButton")
        else:
            self.run_button.config(text="Run", command=self.run, style="Run.TButton")

    def _render_status_ok(self):
        for lbl in self.status_frame.grid_slaves():
            lbl.destroy()
        self.status_labels = {}
        ok_label = ttk.Label(self.status_frame, text="Status: OK", foreground="green")
        ok_label.grid(row=0, column=0, sticky="w")
        self.status_labels["OK"] = ok_label

    def show_status(self, info: Optional[dict]):
        # Clear all on None
        if info is None:
            self._render_status_ok()
            return
        # Remove default OK label once we have a real status
        if "OK" in self.status_labels:
            self.status_labels["OK"].destroy()
            del self.status_labels["OK"]
        key = (info.get("channel"), info.get("data_type"), info.get("status"))
        if key in self.status_labels:
            return
        label_text, tooltip = self._format_status(info)
        self.status_labels[key] = {"text": label_text, "tooltip": tooltip}
        self._render_status_labels()

    def _render_status_labels(self):
        # Clear existing widgets
        for child in self.status_frame.grid_slaves():
            child.destroy()
        if not self.status_labels:
            self._render_status_ok()
            return
        # Sort by channel number (None/ALL/NOCH at end)
        def sort_key(item):
            (ch, dt, st), meta = item
            # Place numeric channels first in ascending order; others after
            try:
                return (0, int(ch))
            except Exception:
                return (1, 0 if ch is None else ch)

        for col, ((ch, dt, st), meta) in enumerate(sorted(self.status_labels.items(), key=sort_key)):
            lbl = ttk.Label(self.status_frame, text=meta["text"], foreground="red", padding=(2, 0))
            lbl.grid(row=0, column=col, sticky="w", padx=(0, 6))
            attach_tooltip(lbl, meta["tooltip"])

    def _format_status(self, info: dict) -> tuple[str, str]:
        ch = info.get("channel")
        dt = info.get("data_type")
        status = info.get("status")
        desc = info.get("desc", "")
        if ch is None or ch == B1500Session.CH_NOCH:
            ch_label = "N/A"
        elif ch == B1500Session.CH_ALL:
            ch_label = "ALL"
        else:
            ch_label = self.lookup_smu_label(ch)
        dt_desc = B1500Session.describe_data_type_short(dt) if dt is not None else "T?"
        label = f"{ch_label} {dt_desc} 0x{status:X}"
        tooltip = f"{ch_label} | {B1500Session.describe_data_type(dt)} | {desc} (0x{status:X})"
        return label, tooltip

    # Live plotting helpers wired via MeasurementRunner callbacks
    def start_plot(self, title, xlabel, ylabel, series_label="Data", styles=None, secondary_series=None, secondary_ylabel=None, secondary_yscale=None, series_labels=None):
        spec = PlotSpec(
            title=title,
            xlabel=xlabel,
            ylabel=ylabel,
            primary_series=series_label or "Data",
            styles=styles or {},
            secondary_series=secondary_series or [],
            secondary_ylabel=secondary_ylabel,
            secondary_yscale=secondary_yscale,
            initial_series=series_labels if series_labels is not None else ([series_label] if series_label else []),
        )
        self.plot.start(spec)

    def add_plot_point(self, x, y, series_label="Data"):
        self.plot.add_point(x, y, series_label)

    def add_plot_series(self, xs, ys, series_label="Data"):
        self.plot.add_series(xs, ys, series_label)

    def finish_plot(self, save_path=None):
        self.plot.finish(save_path)
        if save_path:
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
        if 'run_subsite' in last_sel:
            self.run_subsite_var.set(bool(last_sel['run_subsite']))
        if 'set_home_before_run' in last_sel:
            self.set_home_var.set(bool(last_sel['set_home_before_run']))
        if 'chip' in last_sel:
            self.chip_var.set(last_sel['chip'])

    def build_last_selection(self):
        """Capture current UI selections; new fields are automatically persisted."""
        return {
            'site': self.site_var.get(),
            'subsite': self.subsite_var.get(),
            'device': self.device_var.get(),
            'procedure': self.proc_var.get(),
            'run_subsite': self.run_subsite_var.get(),
            'set_home_before_run': self.set_home_var.get(),
            'chip': self.chip_var.get(),
        }

    def load_global_asu(self):
        asu_ch = self.config.data.get('asu_channels', [])
        # Display as comma-separated
        self.asu_channels_var.set(','.join(map(str, asu_ch)) if asu_ch else '')
        self.asu_path_var.set('' if self.config.data.get('asu_path_mode') is None else str(self.config.data.get('asu_path_mode')))
        self.asu_range_var.set(bool(self.config.data.get('asu_range_mode')))

    def update_global_asu_from_ui(self):
        # Parse channels list (accept labels or numbers)
        raw = self.asu_channels_var.get().strip()
        chans = []
        if raw:
            for token in raw.split(','):
                tok = token.strip()
                if not tok:
                    continue
                # Store the raw token to preserve labels; mapping happens at use time
                chans.append(tok)
        path_val = self.asu_path_var.get().strip()
        range_val = self.asu_range_var.get()
        self.config.data['asu_channels'] = chans
        self.config.data['asu_path_mode'] = None if path_val == '' else int(float(path_val))
        # Treat checkbox True as enabling the 1pA range (set to 1), False as None/disabled
        self.config.data['asu_range_mode'] = 1 if range_val else None


if __name__ == '__main__':
    root = tk.Tk()
    app = MainUI(root)
    root.mainloop()
