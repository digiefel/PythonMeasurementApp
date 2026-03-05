import json
import os
import threading
from datetime import datetime
import time
import tkinter as tk
from tkinter import ttk, filedialog
from tkinter import messagebox
from typing import Optional
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from ui_temperature import TemperatureUI
from ui_device_selection import DeviceSelectionDialog

from config import Config
from runner import MeasurementRunner
from bindings import (
    SMU_CHANNEL_MAP,
    WGFMU_CHANNEL_MAP,
    B1500_VOLTAGE_RANGES,
    B1500_CURRENT_RANGES,
    WGFMU_MEASURE_VOLTAGE_RANGES,
    WGFMU_MEASURE_CURRENT_RANGES,
    B1500Session,
)
from procedures.base import MeasurementAbortRequested
from procedures.rv_sweep import RVSweepProcedure
from procedures.four_terminal_iv_sweep import FourTerminalIVProcedure
from procedures.oxide_breakdown import OxideBreakdownProcedure
from procedures.PUND import PUNDProcedure
from procedures.pund_fatigue import PUNDFatigueProcedure
from tooltip_helper import attach_tooltip
from plot_manager import PlotManager, PlotSpec


class MainUI:
    def __init__(self, root):
        self.root = root
        self.config = Config('global_config.json', 'TASE_devices.csv')
        self.runner = MeasurementRunner(self.config)
        self.runner.log_callback = self._post_log
        self.runner.plot_start_callback = self._post_plot_start
        self.runner.plot_point_callback = self._post_plot_point
        self.runner.plot_series_callback = self._post_plot_series
        self.runner.plot_finalize_callback = self._post_plot_finish
        self.runner.plot_limits_callback = self._post_plot_limits
        self.runner.plot_append_callback = self._post_plot_append
        self.runner.status_callback = self._post_status
        self.runner.contact_state_callback = lambda state: self._post(self._set_contact_state, state)
        self.runner.light_state_callback = lambda state: self._post(self._set_light_state, state)
        self._run_thread = None
        # Selected devices for custom runs (device names)
        self.selected_device_names = set()

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
        self.set_home_var = tk.BooleanVar(value=False)
        self.prober_contact_state = tk.BooleanVar(value=False)
        self.prober_light_state = tk.BooleanVar(value=True)
        self.position_var = tk.StringVar(value="X=-- , Y=--")
        self.chip_var = tk.StringVar()
        # Temperature compensation coefficients (um / C)
        self.temp_comp_x_var = tk.StringVar(value="0.0")
        self.temp_comp_y_var = tk.StringVar(value="0.0")
        self.temp_comp_z_var = tk.StringVar(value="0.0")
        # Temperature UI helper
        self.temp_ui = TemperatureUI(self.root, self.runner, self.log)

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
                ('sense_high_channel', 'Sense High SMU', 'smu'),
                ('force_low_channel', 'Force Low SMU', 'smu'),
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
            'PUND': [
                ('gpib_address', 'GPIB Address', str),
                ('channel_1', 'WGFMU Channel 1 (PG Vmeas)', 'wgfmu_channel'),
                ('channel_2', 'WGFMU Channel 2 (FastIV Imeas)', 'wgfmu_channel'),
                ('vmax', 'Vmax (V)', float),
                ('frequency', 'Frequency (Hz)', float),
                ('pulse_delay', 'Pulse Delay (s)', float),
                ('repetition_count', 'Repetition Count', int),
                ('repetition_delay', 'Repetition Delay (s)', float),
                ('invert_polarity', 'Invert Polarity (PNNPP)', bool),
                ('meas_range_1', 'Meas Range Ch1 (V)', 'wgfmu_voltage_range'),
                ('meas_range_2', 'Meas Range Ch2 (I)', 'wgfmu_current_range'),
            ],
            'PUNDFatigue': [
                ('gpib_address', 'GPIB Address', str),
                ('channel_1', 'WGFMU Channel 1 (PG Vmeas)', 'wgfmu_channel'),
                ('channel_2', 'WGFMU Channel 2 (FastIV Imeas)', 'wgfmu_channel'),
                ('vmax', 'Vmax (V)', float),
                ('frequency', 'Frequency (Hz)', float),
                ('pulse_delay', 'Pulse Delay (s)', float),
                ('cycle_count', 'Cycle Count', float),
                ('invert_polarity', 'Invert Polarity (PNNPP)', bool),
                ('points_per_decade', 'Points per Decade', int),
                ('meas_range_1', 'Meas Range Ch1 (V)', 'wgfmu_voltage_range'),
                ('meas_range_2', 'Meas Range Ch2 (I)', 'wgfmu_current_range'),
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
                'sense_high_channel': 5,
                'force_low_channel': 3,
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
            'PUND': {
                'gpib_address': 'GPIB0::17::INSTR',
                'channel_1': 101,
                'channel_2': 102,
                'vmax': 1.0,
                'frequency': 1e3,
                'pulse_delay': 0.0,
                'repetition_count': 1,
                'repetition_delay': 0.0,
                'invert_polarity': False,
                'meas_range_1': WGFMU_MEASURE_VOLTAGE_RANGES[0][0],
                'meas_range_2': WGFMU_MEASURE_CURRENT_RANGES[0][0],
            },
            'PUNDFatigue': {
                'gpib_address': 'GPIB0::17::INSTR',
                'channel_1': 101,
                'channel_2': 102,
                'vmax': 1.0,
                'frequency': 1e3,
                'pulse_delay': 0.0,
                'cycle_count': 1e6,
                'invert_polarity': False,
                'points_per_decade': 10,
                'meas_range_1': WGFMU_MEASURE_VOLTAGE_RANGES[0][0],
                'meas_range_2': WGFMU_MEASURE_CURRENT_RANGES[0][0],
            },
        }

        self.build_layout()
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

        ttk.Checkbutton(self.selection_frame, text="Set subsite origin at start", variable=self.set_home_var).grid(row=8, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # Device selection button and label
        device_sel_frame = ttk.Frame(self.selection_frame)
        device_sel_frame.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        device_sel_frame.grid_columnconfigure(0, weight=1, uniform="devsel")
        device_sel_frame.grid_columnconfigure(1, weight=1, uniform="devsel")
        
        ttk.Button(device_sel_frame, text="Device Selection...", command=self.open_device_selection).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.selected_devices_label = ttk.Label(device_sel_frame, text="")
        self.selected_devices_label.grid(row=0, column=1, sticky="w", padx=(4, 0))

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
        self.temp_ui.build_panel(self.selection_temp_frame)

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
        self.contact_button.grid(row=0, column=0, sticky="ew", padx=4, pady=2)
        self.light_button = tk.Button(prober_frame, text="Light ON", command=self.toggle_prober_light, bg="green yellow", fg="black")
        self.light_button.grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        ttk.Button(prober_frame, text="Go To Device", command=self.prober_go_to_device).grid(row=1, column=0, sticky="ew", padx=4, pady=2)
        ttk.Button(prober_frame, text="Set Reference to Device", command=self.prober_set_reference).grid(row=1, column=1, sticky="ew", padx=2, pady=2)
        ttk.Button(prober_frame, text="Read Position", command=self.read_position).grid(row=2, column=0, sticky="ew", padx=4, pady=2)
        ttk.Label(prober_frame, textvariable=self.position_var).grid(row=2, column=1, sticky="w", padx=4, pady=2)
        comp_frame = ttk.Frame(prober_frame)
        comp_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=4, pady=(8, 2))
        for c in range(3):
            comp_frame.grid_columnconfigure(c, weight=1)
        ttk.Label(comp_frame, text="CompX (um / C)").grid(row=0, column=0, sticky="w", padx=2, pady=(0, 2))
        ttk.Label(comp_frame, text="CompY (um / C)").grid(row=0, column=1, sticky="w", padx=2, pady=(0, 2))
        ttk.Label(comp_frame, text="CompZ (um / C)").grid(row=0, column=2, sticky="w", padx=2, pady=(0, 2))
        ttk.Entry(comp_frame, textvariable=self.temp_comp_x_var, width=10).grid(row=1, column=0, sticky="ew", padx=2, pady=(0, 2))
        ttk.Entry(comp_frame, textvariable=self.temp_comp_y_var, width=10).grid(row=1, column=1, sticky="ew", padx=2, pady=(0, 2))
        ttk.Entry(comp_frame, textvariable=self.temp_comp_z_var, width=10).grid(row=1, column=2, sticky="ew", padx=2, pady=(0, 2))

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
        # Clear selected devices when subsite changes
        self.selected_device_names.clear()
        self._update_selected_devices_label()

    def _update_selected_devices_label(self):
        """Update the label showing how many devices are selected."""
        count = len(self.selected_device_names)
        if count == 0:
            self.selected_devices_label.config(text="")
        elif count == 1:
            self.selected_devices_label.config(text=f"✓ 1 device selected")
        else:
            self.selected_devices_label.config(text=f"✓ {count} devices selected")

    def open_device_selection(self):
        """Open the device selection dialog."""
        site = next((s for s in self.config.sites if s.name == self.site_var.get()), None)
        subsite = next((sub for sub in site.subsites if sub.name == self.subsite_var.get()), None) if site else None
        if not subsite or not subsite.devices:
            messagebox.showwarning("No Devices", "Please select a subsite with devices first.")
            return
        
        # Get currently selected device (used for origin if "set subsite origin" is checked)
        device = next((d for d in subsite.devices if d.name == self.device_var.get()), None) if subsite else None
        set_home_checked = self.set_home_var.get()
        
        # Get current prober position
        prober_pos = None
        try:
            pos = self.runner.prober_read_position()
            if pos:
                origin = self.runner.prober_ctrl.subsite_origin
                
                if set_home_checked and device:
                    # Simulate what will happen when "set subsite origin at start" runs:
                    # new_origin = current_abs_pos - device_offset
                    # After that, prober_rel = current_abs_pos - new_origin = device_offset
                    # 
                    # But we need to show where the prober CURRENTLY is relative to devices.
                    # If prober is at absolute pos P and we're about to set origin O = P - device_offset,
                    # then after origin is set: prober_rel = P - O = device_offset
                    # 
                    # So if the prober is currently at the device we're setting origin to,
                    # the prober_rel will equal that device's coordinates.
                    # 
                    # Formula: new_prober_rel = abs_pos - (abs_pos - device_offset) = device_offset
                    # But abs_pos is NOT the device position necessarily - user might be anywhere.
                    # 
                    # Let's compute where prober will appear relative to device coordinates:
                    # If current origin exists: abs_pos = origin + current_rel
                    # New origin = abs_pos - device_offset
                    # New rel = abs_pos - new_origin = abs_pos - (abs_pos - device_offset) = device_offset
                    # 
                    # Wait, that's wrong. The new origin is set based on WHERE the prober is NOW,
                    # offset by the selected device's coords. So:
                    # new_origin = abs_pos - selected_device_offset
                    # new_rel_for_any_device = abs_pos - new_origin = selected_device_offset
                    #
                    # This means: after setting origin, the prober will appear at coordinates
                    # equal to the selected device's offset. If prober is at D4 and we set origin
                    # to D4, prober will show at D4's coords (-480, 480).
                    #
                    # But this only works if the prober IS at the selected device. If prober is
                    # elsewhere, we need: new_rel = abs_pos - new_origin = abs_pos - (abs_pos - device_offset) = device_offset
                    # Hmm, that still gives device_offset regardless of where prober is. That's wrong.
                    #
                    # Let me re-read set_subsite_origin:
                    # subsite_origin = current_pos - device_offset
                    # This means: "the origin point is at (current_pos - device_offset)"
                    # Then when we want to go to a device: target = origin + device_coords
                    # 
                    # For current prober position: prober_rel = current_pos - origin
                    #                            = current_pos - (current_pos - device_offset) 
                    #                            = device_offset
                    #
                    # So the prober's new relative position = the device offset used to set origin.
                    # This is correct - if you set origin while at D4, you're saying "I'm at D4".
                    
                    prober_pos = (device.x, device.y)
                elif origin:
                    # Origin already set, compute relative position
                    prober_pos = (pos[0] - origin[0], pos[1] - origin[1])
                else:
                    # No origin set and not simulating - show absolute position
                    # This won't align with device coords but shows raw prober position
                    prober_pos = pos
        except Exception as e:
            self.log(f"Could not read prober position: {e}")
        
        # Open the dialog
        dialog = DeviceSelectionDialog(
            self.root,
            subsite.devices,
            prober_position=prober_pos,
            initially_selected=self.selected_device_names
        )
        
        # Set up refresh callback
        def refresh_prober():
            try:
                pos = self.runner.prober_read_position()
                if pos:
                    origin = self.runner.prober_ctrl.subsite_origin
                    
                    if set_home_checked and device:
                        # Same simulation as above
                        dialog.update_prober_position((device.x, device.y))
                    elif origin:
                        dialog.update_prober_position((pos[0] - origin[0], pos[1] - origin[1]))
                    else:
                        dialog.update_prober_position(pos)
            except Exception as e:
                self.log(f"Could not refresh prober position: {e}")
        
        dialog.set_refresh_callback(refresh_prober)
        
        result = dialog.show()
        if result is not None:
            self.selected_device_names = result
            self._update_selected_devices_label()
            if len(result) > 0:
                self.log(f"Selected {len(result)} device(s): {', '.join(sorted(result))}")

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
            elif cast == 'wgfmu_voltage_range':
                label_val = self.lookup_range_label(val, WGFMU_MEASURE_VOLTAGE_RANGES)
                var = tk.StringVar(value=label_val)
                combo = ttk.Combobox(self.params_frame, textvariable=var, values=[label for _, label in WGFMU_MEASURE_VOLTAGE_RANGES], state="readonly")
                combo.grid(row=idx, column=1, sticky="ew", padx=4, pady=2)
                self.param_vars[key] = (var, cast)
            elif cast == 'wgfmu_channel':
                label_val = self.lookup_wgfmu_label(val)
                var = tk.StringVar(value=label_val)
                combo = ttk.Combobox(self.params_frame, textvariable=var, values=list(WGFMU_CHANNEL_MAP.keys()), state="readonly")
                combo.grid(row=idx, column=1, sticky="ew", padx=4, pady=2)
                self.param_vars[key] = (var, cast)
            elif cast == 'wgfmu_current_range':
                label_val = self.lookup_range_label(val, WGFMU_MEASURE_CURRENT_RANGES)
                var = tk.StringVar(value=label_val)
                combo = ttk.Combobox(self.params_frame, textvariable=var, values=[label for _, label in WGFMU_MEASURE_CURRENT_RANGES], state="readonly")
                combo.grid(row=idx, column=1, sticky="ew", padx=4, pady=2)
                self.param_vars[key] = (var, cast)
            else:
                var = tk.StringVar(value=str(val))
                entry = ttk.Entry(self.params_frame, textvariable=var)
                entry.grid(row=idx, column=1, sticky="ew", padx=4, pady=2)
                self.params_frame.grid_columnconfigure(1, weight=1)
                self.param_vars[key] = (var, cast)

        # Add preview button for PUNDFatigue
        if proc_name == 'PUNDFatigue':
            row_idx = len(fields)
            preview_btn = ttk.Button(self.params_frame, text="Preview Sequence", command=self._show_pund_fatigue_preview)
            preview_btn.grid(row=row_idx, column=0, columnspan=2, pady=10)

    def _show_pund_fatigue_preview(self):
        """Show preview dialog for PUNDFatigue measurement schedule."""
        try:
            cycle_count = float(self.param_vars.get('cycle_count', (tk.StringVar(value='1e6'), float))[0].get())
            frequency = float(self.param_vars.get('frequency', (tk.StringVar(value='1e3'), float))[0].get())
            ppd = int(float(self.param_vars.get('points_per_decade', (tk.StringVar(value='10'), int))[0].get()))
        except ValueError as e:
            messagebox.showerror("Invalid Parameters", f"Could not parse parameters: {e}")
            return

        preview = PUNDFatigueProcedure.get_preview_info(cycle_count, frequency, ppd)
        measure_cycles = preview['measure_cycles']

        # Format duration
        total_sec = preview['total_duration']
        if total_sec < 60:
            duration_str = f"{total_sec:.1f} s"
        elif total_sec < 3600:
            duration_str = f"{total_sec/60:.1f} min"
        else:
            duration_str = f"{total_sec/3600:.2f} h"

        # Build message
        lines = [
            f"Cycle Count: {cycle_count:.2e}",
            f"Frequency: {frequency:.0f} Hz",
            f"Points per Decade: {ppd}",
            f"Decades: {preview['decades']:.1f}",
            f"",
            f"Total Measurements: {preview['total_measurements']}",
            f"Estimated Duration: {duration_str}",
            f"",
            f"Measurement at cycles:",
        ]

        # Show cycles in compact form
        if len(measure_cycles) <= 20:
            lines.append("  " + ", ".join(str(c) for c in measure_cycles))
        else:
            # Show first 10 and last 10
            first = ", ".join(str(c) for c in measure_cycles[:10])
            last = ", ".join(str(c) for c in measure_cycles[-10:])
            lines.append(f"  {first}")
            lines.append(f"  ... ({len(measure_cycles) - 20} more)")
            lines.append(f"  {last}")

        messagebox.showinfo("PUND Fatigue Preview", "\n".join(lines))

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
                elif cast == 'wgfmu_voltage_range':
                    settings[key] = self.lookup_range_value(var.get(), WGFMU_MEASURE_VOLTAGE_RANGES)
                elif cast == 'wgfmu_channel':
                    settings[key] = WGFMU_CHANNEL_MAP.get(var.get(), var.get())
                elif cast == 'wgfmu_current_range':
                    settings[key] = self.lookup_range_value(var.get(), WGFMU_MEASURE_CURRENT_RANGES)
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
            title="Load settings",
            initialdir=self.config.config_root
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
        try:
            self._apply_temp_comp()
        except ValueError:
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
        temp_info = self.temp_ui.collect_run_inputs()
        if temp_info is None:
            return
        temp_enabled, temp_list, wait_after, temp_mode = temp_info

        proc_class = {
            'RVSweep': RVSweepProcedure,
            'FourTerminalIV': FourTerminalIVProcedure,
            'OxideBreakdown': OxideBreakdownProcedure,
            'PUND': PUNDProcedure,
            'PUNDFatigue': PUNDFatigueProcedure,
        }[proc_name]
        settings = self.collect_settings()
        # Cache current settings/selection in memory only to avoid overwriting config files on run
        self.config.data.setdefault('procedures', {})[proc_name] = settings
        self.config.data['last_selection'] = self.build_last_selection()
        set_home = self.set_home_var.get()
        
        # Determine which devices to run (always a list)
        if self.selected_device_names:
            # Use selected devices (in their original order from subsite)
            devices_to_run = [d for d in subsite.devices if d.name in self.selected_device_names]
        else:
            devices_to_run = [device]
        
        device_count = len(devices_to_run)
        if self._run_thread and self._run_thread.is_alive():
            self.log("A run is already in progress.")
            return
        # Start live temperature polling if applicable
        poll_interval = 1.0
        if temp_enabled:
            self.temp_ui.start_run(temp_list, wait_after, device_count=device_count)
        else:
            self.temp_ui.stop_run()
        def target():
            self.runner.prober_set_light(False)
            if set_home:
                self._post_log(f"Setting subsite origin to device '{device.name}' at ({device.x}um, {device.y}um).")
                self.runner.set_subsite_origin(device.x, device.y)
            try:
                if temp_enabled:
                    self.runner.run_temperature_sweep(
                        temp_list,
                        wait_after,
                        chip_id,
                        site,
                        subsite,
                        proc_class,
                        settings,
                        devices_to_run=devices_to_run,
                        poll_interval_s=poll_interval
                    )
                else:
                    self.runner.current_temp_c = None
                    self.runner.run_devices(chip_id, site, subsite, devices_to_run, proc_class, settings)
            except MeasurementAbortRequested:
                self._post_log('Run aborted by user.')
            except Exception as e:
                self._post_log(f'Run error: {e}')
                raise
            finally:
                self.runner.prober_set_light(True)
                self.runner.stop_event.clear()  # Clear stop flag now that we're done
                self._post(lambda: None)  # ensure main loop wakes
                self._run_thread = None
                self._post(self._set_running_state, False)
                self._post(self.temp_ui.stop_run)
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
        try:
            self._apply_temp_comp()
        except ValueError:
            return
        try:
            self.runner.move_to_device(device)
        except Exception as e:
            self.log(f"Prober move failed: {e}")
            messagebox.showerror("Prober move", str(e))

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

    def toggle_prober_light(self):
        state = self.runner.prober_toggle_light()
        if state is None:
            self.log("Could not toggle scope light.")
            return
        self._set_light_state(state)

    def _set_light_state(self, light_on: bool):
        self.prober_light_state.set(light_on)
        if light_on:
            self.light_button.config(text="Light ON", bg="green yellow")
        else:
            self.light_button.config(text="Light OFF", bg="yellow")

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

    def _post_plot_limits(self, *args, **kwargs):
        self._post(self.set_plot_limits, *args, **kwargs)

    def _post_plot_append(self, *args, **kwargs):
        self._post(self.append_plot_points, *args, **kwargs)

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
        self.plot.append_point(x, y, series_label)

    def add_plot_series(self, xs, ys, series_label="Data"):
        self.plot.add_series(xs, ys, series_label)

    def set_plot_limits(self, xlim=None, ylim=None, y2lim=None):
        self.plot.set_limits(xlim, ylim, y2lim)

    def append_plot_points(self, points: dict):
        self.plot.append_points(points)

    def finish_plot(self, filename: str | None, output_root: str, output_relative: str, fallback_root: str):
        if not filename:
            self.plot.finish(None)
            return
        primary_path = os.path.join(output_root, output_relative, filename)
        try:
            os.makedirs(os.path.dirname(primary_path), exist_ok=True)
            self.plot.finish(primary_path)
            self.log(f'Plot saved to {primary_path}')
        except Exception as e:
            fallback_path = os.path.join(fallback_root, output_relative, filename)
            try:
                os.makedirs(os.path.dirname(fallback_path), exist_ok=True)
                self.log(f"Warning: plot save failed ({e}); retrying at {fallback_path}")
                self.plot.finish(fallback_path)
                self.log(f'Plot saved to fallback {fallback_path}')
            except Exception as e2:
                self.log(f"Plot fallback save failed: {e2}")
                self.runner.safe_stop()
                raise

    # Helpers
    def lookup_smu_label(self, value):
        # Accept already a label, or map numeric back to label
        if value in SMU_CHANNEL_MAP:
            return value
        for label, ch in SMU_CHANNEL_MAP.items():
            if str(ch) == str(value):
                return label
        return next(iter(SMU_CHANNEL_MAP.keys()))

    def lookup_wgfmu_label(self, value):
        # Accept already a label, or map numeric back to label
        if value in WGFMU_CHANNEL_MAP:
            return value
        for label, ch in WGFMU_CHANNEL_MAP.items():
            if str(ch) == str(value):
                return label
        return next(iter(WGFMU_CHANNEL_MAP.keys()))

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

    # Temperature UI logic is encapsulated in TemperatureUI (ui_temperature.py)
    def _on_close(self):
        self.root.withdraw()
        self.temp_ui.stop_run()
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
        if 'set_home_before_run' in last_sel:
            self.set_home_var.set(bool(last_sel['set_home_before_run']))
        if 'chip' in last_sel:
            self.chip_var.set(last_sel['chip'])
        if 'selected_devices' in last_sel:
            self.selected_device_names = set(last_sel['selected_devices'])
            self.update_device_selection_label()
        if 'temp_comp_x_um_per_c' in last_sel:
            self.temp_comp_x_var.set(str(last_sel.get('temp_comp_x_um_per_c', '0.0')))
        if 'temp_comp_y_um_per_c' in last_sel:
            self.temp_comp_y_var.set(str(last_sel.get('temp_comp_y_um_per_c', '0.0')))
        if 'temp_comp_z_um_per_c' in last_sel:
            self.temp_comp_z_var.set(str(last_sel.get('temp_comp_z_um_per_c', '0.0')))
        self.temp_ui.apply_last_selection(last_sel)

    def build_last_selection(self):
        """Capture current UI selections; new fields are automatically persisted."""
        data = {
            'site': self.site_var.get(),
            'subsite': self.subsite_var.get(),
            'device': self.device_var.get(),
            'procedure': self.proc_var.get(),
            'set_home_before_run': self.set_home_var.get(),
            'chip': self.chip_var.get(),
            'selected_devices': list(self.selected_device_names),
        }
        data['temp_comp_x_um_per_c'] = self.temp_comp_x_var.get()
        data['temp_comp_y_um_per_c'] = self.temp_comp_y_var.get()
        data['temp_comp_z_um_per_c'] = self.temp_comp_z_var.get()
        data.update(self.temp_ui.build_last_selection_fragment())
        return data

    def _apply_temp_comp(self):
        try:
            cx = float(self.temp_comp_x_var.get())
            cy = float(self.temp_comp_y_var.get())
            cz = float(self.temp_comp_z_var.get())
        except ValueError:
            messagebox.showerror("Temperature compensation", "Compensation coefficients must be numeric.")
            raise
        self.log(f"applied temp compensation: {cx}, {cy}, {cz}")
        self.runner.set_temp_compensation(cx, cy, cz)

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
