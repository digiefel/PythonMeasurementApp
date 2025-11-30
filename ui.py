import json
import os
import threading
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog
from tkinter import messagebox
from typing import Optional
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

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

        self.root.title("Python Measurement App")
        self.root.geometry("1400x900")
        for col, weight in enumerate((1, 1, 2)):
            self.root.grid_columnconfigure(col, weight=weight)
        self.root.grid_rowconfigure(0, weight=3)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_rowconfigure(2, weight=1)
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
        # Temperature state
        self.temp_enabled_var = tk.BooleanVar(value=False)
        self.temp_mode_var = tk.StringVar(value="Setpoint")
        self.temp_setpoint_var = tk.StringVar()
        self.temp_sweep_var = tk.StringVar()
        self.temp_wait_var = tk.StringVar(value="0")
        self.temp_value_var = tk.StringVar(value="--")
        self.temp_setpoint_display_var = tk.StringVar(value="--")
        self._temp_poll_job = None

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
        self._toggle_temp_controls()
        # Start background temperature polling immediately so the readout is populated
        self._start_temp_polling(self._safe_poll_interval())
        # React to sweep entry edits to refresh the tiny profile
        self.temp_sweep_var.trace_add('write', lambda *_: self._update_sweep_plot())
        self._update_sweep_plot()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
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
        self._init_contact_state()

    def _init_contact_state(self):
        """Query prober for actual contact status and update button accordingly."""
        try:
            height = self.runner.get_chuck_height()
            if height is not None:
                has_contact = height >= -1.0 # contact if Z <= 1um (inverted)
                self._set_contact_state(has_contact)
        except Exception as e:
            self.log(f"Could not read initial contact state: {e}")

    def build_layout(self):
        # Selection section
        self.selection_temp_frame = ttk.Frame(self.root)
        self.selection_temp_frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.selection_temp_frame.grid_rowconfigure(0, weight=3)
        self.selection_temp_frame.grid_rowconfigure(1, weight=1)
        self.selection_temp_frame.grid_columnconfigure(0, weight=1)

        self.selection_frame = ttk.LabelFrame(self.selection_temp_frame, text="Selection")
        self.selection_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
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

        self.run_button = tk.Button(self.selection_frame, text="RUN", command=self.run, bg="green", fg="white")
        self.run_button.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        # Temperature controls (separate section below Selection)
        self.temp_enable_cb = ttk.Checkbutton(self.selection_temp_frame, text="Temperature", variable=self.temp_enabled_var, command=self._toggle_temp_controls)
        temp_frame = ttk.LabelFrame(self.selection_temp_frame, labelwidget=self.temp_enable_cb)
        temp_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=6)
        temp_frame.grid_columnconfigure(0, weight=1)
        temp_frame.grid_columnconfigure(1, weight=1)
        ttk.Label(temp_frame, text="Mode").grid(row=0, column=0, sticky="w", padx=2, pady=2)
        self.temp_mode_cb = ttk.Combobox(temp_frame, textvariable=self.temp_mode_var, values=["Setpoint", "Sweep"], state="readonly")
        self.temp_mode_cb.grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        self.temp_mode_cb.bind('<<ComboboxSelected>>', lambda e=None: self._toggle_temp_controls())
        self.temp_setpoint_entry_label = ttk.Label(temp_frame, text="Setpoint (C)")
        self.temp_setpoint_entry_label.grid(row=1, column=0, sticky="w", padx=2, pady=2)
        self.temp_setpoint_entry = ttk.Entry(temp_frame, textvariable=self.temp_setpoint_var)
        self.temp_setpoint_entry.grid(row=1, column=1, sticky="ew", padx=2, pady=2)
        self.temp_sweep_entry_label = ttk.Label(temp_frame, text="Sweep list (C)")
        self.temp_sweep_entry_label.grid(row=2, column=0, sticky="w", padx=2, pady=2)
        self.temp_sweep_entry = ttk.Entry(temp_frame, textvariable=self.temp_sweep_var)
        self.temp_sweep_entry.grid(row=2, column=1, sticky="ew", padx=2, pady=2)
        ttk.Label(temp_frame, text="Wait after stable (s)").grid(row=3, column=0, sticky="w", padx=2, pady=2)
        self.temp_wait_entry = ttk.Entry(temp_frame, textvariable=self.temp_wait_var)
        self.temp_wait_entry.grid(row=3, column=1, sticky="ew", padx=2, pady=2)
        self.temp_set_button = ttk.Button(temp_frame, text="Set Temperature", command=self._set_temperature_now)
        self.temp_set_button.grid(row=5, column=0, columnspan=2, sticky="ew", padx=2, pady=(4, 2))
        temp_row = ttk.Frame(temp_frame)
        temp_row.grid(row=6, column=0, columnspan=2, sticky="ew", padx=2, pady=(2, 0))
        for c in range(4):
            temp_row.grid_columnconfigure(c, weight=1)
        ttk.Label(temp_row, text="Temp:").grid(row=0, column=0, sticky="w", padx=2)
        self.temp_value_label = ttk.Label(temp_row, textvariable=self.temp_value_var)
        self.temp_value_label.grid(row=0, column=1, sticky="w", padx=2)
        ttk.Label(temp_row, text="Setpoint:").grid(row=0, column=2, sticky="e", padx=2)
        self.temp_setpoint_display_label = ttk.Label(temp_row, textvariable=self.temp_setpoint_display_var)
        self.temp_setpoint_display_label.grid(row=0, column=3, sticky="e", padx=2)
        # Tiny sweep profile plot (shown only in Sweep mode)
        self.temp_profile_fig = Figure(figsize=(2.0, 0.8), dpi=100, layout='compressed')
        self.temp_profile_ax = self.temp_profile_fig.add_subplot(111)
        self.temp_profile_ax.tick_params(axis='both', labelsize=7)
        self.temp_profile_ax.spines["top"].set_visible(False)
        self.temp_profile_ax.spines["right"].set_visible(False)
        self.temp_profile_canvas = FigureCanvasTkAgg(self.temp_profile_fig, master=temp_frame)
        self.temp_profile_widget = self.temp_profile_canvas.get_tk_widget()
        self.temp_profile_widget.grid(row=7, column=0, columnspan=2, sticky="ew", padx=2, pady=(2, 2))
        # Make background transparent to blend with Tk
        self.temp_profile_fig.patch.set_alpha(0)
        self.temp_profile_ax.set_facecolor("none")
        self.temp_profile_widget.configure(bg=self.root.cget('bg'), highlightthickness=0)

        # Procedure settings section
        self.params_frame = ttk.LabelFrame(self.root, text="Procedure Settings")
        self.params_frame.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        self.params_frame.grid_columnconfigure(0, weight=1)
        self.params_frame.grid_columnconfigure(1, weight=1)

        # Matplotlib figure embedded in Tk (managed by PlotManager)
        self.plot = PlotManager(self.root)
        self.canvas_widget = self.plot.canvas_widget
        self.canvas_widget.grid(row=0, column=2, rowspan=1, padx=8, pady=8, sticky="nsew")
        self.canvas_widget.configure(bg=self.root.cget('bg'), highlightthickness=0)

        # Prober controls (bottom left)
        prober_frame = ttk.LabelFrame(self.root, text="Prober Control")
        prober_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        for c in range(2):
            prober_frame.grid_columnconfigure(c, weight=1)
        self.contact_button = tk.Button(prober_frame, text="CONTACT", command=self.toggle_contact, bg="yellow", fg="black")
        self.contact_button.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=2)
        ttk.Button(prober_frame, text="Go To Device", command=self.prober_go_to_device).grid(row=1, column=0, sticky="ew", padx=4, pady=2)
        ttk.Button(prober_frame, text="Set Reference to Device", command=self.prober_set_reference).grid(row=1, column=1, sticky="ew", padx=2, pady=2)
        ttk.Button(prober_frame, text="Read Position", command=self.read_position).grid(row=2, column=0, sticky="ew", padx=4, pady=2)
        ttk.Label(prober_frame, textvariable=self.position_var).grid(row=2, column=1, sticky="w", padx=4, pady=2)

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
        temp_enabled = self.temp_enabled_var.get()
        temp_mode = self.temp_mode_var.get()
        if temp_mode not in ("Setpoint", "Sweep"):
            temp_mode = "Setpoint"
            self.temp_mode_var.set(temp_mode)
        try:
            wait_after = float(self.temp_wait_var.get() or 0.0)
        except ValueError:
            tk.messagebox.showerror("Invalid temperature wait", "Wait after stabilization must be a number.")
            return
        temp_list = []
        if temp_enabled:
            try:
                if temp_mode == "Setpoint":
                    temp_list = [float(self.temp_setpoint_var.get())]
                else:
                    raw = self.temp_sweep_var.get()
                    temp_list = [float(tok.strip()) for tok in raw.split(',') if tok.strip() != ""]
                if not temp_list:
                    raise ValueError("No temperatures provided")
            except Exception:
                tk.messagebox.showerror("Invalid temperature values", "Provide numeric temperature values in °C.")
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
        # Start live temperature polling if applicable
        poll_interval = self._safe_poll_interval()
        if temp_enabled:
            self._start_temp_polling(poll_interval)
        else:
            self._stop_temp_polling()
        def target():
            self.runner.stop_event.clear()
            try:
                if temp_enabled:
                    self.runner.run_temperature_sweep(
                        temp_list,
                        wait_after,
                        chip_id,
                        site,
                        subsite,
                        device,
                        proc_class,
                        settings,
                        set_home_before_run=set_home,
                        run_subsite=run_all,
                        poll_interval_s=poll_interval
                    )
                else:
                    self.runner.current_temp_c = None
                    if run_all:
                        self._post_log("Running entire subsite; align to reference device before start.")
                        self.runner.run_subsite(chip_id, site, subsite, proc_class, settings, set_home)
                    else:
                        self.runner.run_procedure(chip_id, site, subsite, device, proc_class, settings, set_home)
            except Exception as e:
                self._post_log(f'Run error: {e}')
                raise
            finally:
                self._post(lambda: None)  # ensure main loop wakes
                self._run_thread = None
                self._post(self._set_running_state, False)
                self._post(self._stop_temp_polling)
        self._set_running_state(True)
        self._run_thread = threading.Thread(target=target, daemon=True)
        self._run_thread.start()

    def stop_run(self):
        """Triggered by Stop button to abort measurement safely."""
        self.log("Stop button pressed; stopping run...")
        # Run safe_stop in a separate thread to avoid blocking the UI
        threading.Thread(target=self.runner.safe_stop, daemon=True).start()

    # --- Prober control handlers ---
    def prober_set_reference(self):
        # get current device position as dx, dy
        # set home position to -dx, -dy
        site = next((s for s in self.config.sites if s.name == self.site_var.get()), None)
        subsite = next((sub for sub in site.subsites if sub.name == self.subsite_var.get()), None) if site else None
        device = next((d for d in subsite.devices if d.name == self.device_var.get()), None) if subsite else None
        if not device:
            self.log("Select site, subsite, and device before setting reference.")
            return
        self.log(f"Setting prober reference to device '{device.name}' at ({device.x}um, {device.y}um).")
        self.runner.set_subsite_origin(device.x, device.y)

    def prober_go_to_device(self):
        site = next((s for s in self.config.sites if s.name == self.site_var.get()), None)
        subsite = next((sub for sub in site.subsites if sub.name == self.subsite_var.get()), None) if site else None
        device = next((d for d in subsite.devices if d.name == self.device_var.get()), None) if subsite else None
        if not device:
            self.log("Select site, subsite, and device before moving.")
            return
        self.runner.move_to_device(device)

    def toggle_contact(self):
        in_contact = self.prober_contact_state.get()
        if in_contact:
            self.prober_separation()
        else:
            self.prober_contact()

    def prober_contact(self):
        ok = self.runner.prober_contact()
        if ok:
            self._set_contact_state(True)

    def prober_separation(self):
        ok = self.runner.prober_separation()
        if ok:
            self._set_contact_state(False)

    def read_position(self):
        pos = self.runner.prober_read_position()
        if pos:
            x, y = pos
            self.position_var.set(f"X={x:.1f}um , Y={y:.1f}um")
        else:
            self.position_var.set("X=-- , Y=--")
    
    def log(self, msg):
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_msg = f'[{timestamp}] {msg}'

        print(log_msg)
        self.log_text.insert(tk.END, log_msg + '\n')
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
            self.run_button.config(text="STOP", command=self.stop_run, bg="red", fg="white")
        else:
            self.run_button.config(text="RUN", command=self.run, bg="green", fg="white")

    def _set_contact_state(self, in_contact: bool):
        """Update contact button appearance based on contact state."""
        self.prober_contact_state.set(in_contact)
        if in_contact:
            self.contact_button.config(text="CONTACT", bg="green yellow")
        else:
            self.contact_button.config(text="SEPARATION", bg="yellow")

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

    def _update_setpoint_display(self, setpoint_c: Optional[float] = None):
        display = "--" if setpoint_c is None else f"{setpoint_c:.1f} C"
        self.temp_setpoint_display_var.set(display)

    def _update_sweep_plot(self):
        if not self.temp_enabled_var.get():
            self.temp_profile_widget.grid_remove()
            return
        mode = self.temp_mode_var.get()
        try:
            vals = [float(tok.strip()) for tok in self.temp_sweep_var.get().split(",") if tok.strip()]
            vals.append(vals[-1])  # extend last step for visual clarity
        except Exception:
            vals = []
        if mode != "Sweep" or not vals:
            self.temp_profile_widget.grid_remove()
            return
        self.temp_profile_ax.clear()
        xs = list(range(1,len(vals)+1))
        self.temp_profile_ax.set_xticks(xs[:-1])
        self.temp_profile_ax.set_yticks(list(set(vals)))
        self.temp_profile_ax.step(xs, vals, linewidth=1, color='k', where='post')
        self.temp_profile_canvas.draw_idle()
        self.temp_profile_widget.grid(row=7, column=0, columnspan=2, sticky="ew", padx=2, pady=(2, 2))

    def _toggle_temp_controls(self):
        enabled = self.temp_enabled_var.get()
        mode = self.temp_mode_var.get()
        if mode not in ("Setpoint", "Sweep"):
            mode = "Setpoint"
            self.temp_mode_var.set(mode)
        mode_state = "readonly" if enabled else "disabled"
        entry_state = "normal" if enabled else "disabled"
        self.temp_mode_cb.configure(state=mode_state)
        if mode == "Setpoint":
            self.temp_setpoint_entry_label.grid()
            self.temp_setpoint_entry.grid()
            self.temp_sweep_entry_label.grid_remove()
            self.temp_sweep_entry.grid_remove()
            self.temp_setpoint_entry.configure(state=entry_state)
            self.temp_sweep_entry.configure(state="disabled")
        else:
            self.temp_sweep_entry_label.grid()
            self.temp_sweep_entry.grid()
            self.temp_sweep_entry.configure(state=entry_state)
            self.temp_setpoint_entry_label.grid_remove()
            self.temp_setpoint_entry.grid_remove()
            self.temp_setpoint_entry.configure(state="disabled")
        self.temp_wait_entry.configure(state=entry_state)
        self.temp_set_button.configure(state="normal" if enabled else "disabled")
        # Keep polling regardless of toggle so the readout stays populated
        self._start_temp_polling(self._safe_poll_interval())
        self._update_sweep_plot()

    def _set_temperature_now(self):
        mode = self.temp_mode_var.get()
        if mode not in ("Setpoint", "Sweep"):
            mode = "Setpoint"
            self.temp_mode_var.set(mode)
        try:
            if mode == "Setpoint":
                target = float(self.temp_setpoint_var.get())
            else:
                sweep_vals = [float(tok.strip()) for tok in self.temp_sweep_var.get().split(',') if tok.strip() != ""]
                if not sweep_vals:
                    raise ValueError("No sweep temperatures")
                target = sweep_vals[0]
        except Exception as exc:
            tk.messagebox.showerror("Temperature", f"Invalid temperature value: {exc}")
            return
        self.runner.prober_set_temp(target)
        self.log(f"Temperature set to {target:.1f} C")
        if self.temp_enabled_var.get():
            poll = self._safe_poll_interval()
            if poll > 0:
                self._start_temp_polling(poll)
        self._update_setpoint_display()

    def _start_temp_polling(self, poll_interval_s: float):
        self._stop_temp_polling()
        interval_ms = max(int(poll_interval_s * 1000), 250)
        def poll():
            temp = self.runner.prober_get_temp()
            state = self.runner.get_thermo_state()
            setpoint = self.runner.get_temp_setpoint()
            if temp is None:
                self.temp_value_var.set("N/A")
                color = "red"
            else:
                self.temp_value_var.set(f"{temp:.1f} C")
                if state == "heating":
                    color = "orange"
                elif state == "cooling":
                    color = "blue"
                elif state == "controlling":
                    color = "green"
                elif state == "error" or state == "uncontrolled":
                    color = "red"
                else:
                    color = "black"
            self.temp_value_label.configure(foreground=color)
            self._update_setpoint_display(setpoint)
            self._temp_poll_job = self.root.after(interval_ms, poll)
        poll()

    def _stop_temp_polling(self):
        if self._temp_poll_job:
            self.root.after_cancel(self._temp_poll_job)
            self._temp_poll_job = None

    def _safe_poll_interval(self) -> float:
        # val = float(self.temp_poll_var.get() or 1.0)
        # if val < 0.0:
        #     val = 1.0
        return 1.0

    def _on_close(self):
        self.root.withdraw()
        self._stop_temp_polling()
        self.runner.safe_stop()
        if self._run_thread and self._run_thread.is_alive():
            self._run_thread.join(timeout=10)
        self.root.destroy()

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
        if 'temperature_enabled' in last_sel:
            self.temp_enabled_var.set(bool(last_sel.get('temperature_enabled')))
        if 'temperature_mode' in last_sel:
            mode_val = last_sel.get('temperature_mode', 'Setpoint')
            if mode_val not in ("Setpoint", "Sweep"):
                mode_val = "Setpoint"
            self.temp_mode_var.set(mode_val)
        if 'temperature_setpoint_c' in last_sel:
            self.temp_setpoint_var.set(str(last_sel.get('temperature_setpoint_c', '')))
        if 'temperature_sweep_c' in last_sel:
            self.temp_sweep_var.set(str(last_sel.get('temperature_sweep_c', '')))
        if 'temperature_wait_after_s' in last_sel:
            self.temp_wait_var.set(str(last_sel.get('temperature_wait_after_s', 0.0)))
        self._update_setpoint_display()
        self._toggle_temp_controls()

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
            'temperature_enabled': self.temp_enabled_var.get(),
            'temperature_mode': self.temp_mode_var.get(),
            'temperature_setpoint_c': self.temp_setpoint_var.get(),
            'temperature_sweep_c': self.temp_sweep_var.get(),
            'temperature_wait_after_s': self.temp_wait_var.get(),
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
