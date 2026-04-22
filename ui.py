import json
import os
import threading
from datetime import datetime
import time
import re
import tkinter as tk
from tkinter import ttk, filedialog
from tkinter import messagebox
from typing import Optional
from ui_temperature import TemperatureUI
from ui_device_selection import DeviceSelectionDialog

from config import Config
from runner import MeasurementRunner
from instrumentio.codes import B1500_CH_ALL, B1500_CH_NOCH
from instrumentio.constants import (
    SMU_CHANNEL_MAP,
    WGFMU_CHANNEL_MAP,
    B1500_VOLTAGE_RANGES,
    B1500_CURRENT_RANGES,
    B1500_CMU_CHANNELS,
    B1500_CMU_MEASUREMENT_MODES,
    B1500_CMU_INTEGRATION_MODES,
    B1500_CMU_SWEEP_RANGES,
    WGFMU_MEASURE_VOLTAGE_RANGES,
    WGFMU_MEASURE_CURRENT_RANGES,
)
from instrumentio.descriptors import describe_data_type, describe_data_type_short, get_cmu_mode_name
from procedures.base import MeasurementAbortRequested
from procedures.four_terminal_iv_sweep import FourTerminalIVProcedure
from procedures.oxide_breakdown import OxideBreakdownProcedure
from procedures.cv_sweep import CVSweepProcedure
from procedures.PUND import PUNDProcedure
from procedures.pund_fatigue import PUNDFatigueProcedure
from procedures.wgfmu_sampling import WGFMUSamplingProcedure
from tooltip_helper import attach_tooltip
from plotting import PlotBridge

# --- CV Sweep type options ---
CV_SWEEP_TYPES = [
    ('single',    'Single (Start → Stop)'),
    ('double',    'Double (Start → Stop → Start)'),
    ('butterfly', 'Butterfly (0 → Vmax → Vmin → 0)'),
]

# --- Generic SI-prefix helpers ---
_SI_PREFIXES = {
    'T': 1e12, 'G': 1e9, 'M': 1e6, 'k': 1e3, 'K': 1e3,
    'm': 1e-3, 'u': 1e-6, '\u03bc': 1e-6, 'n': 1e-9, 'p': 1e-12,
}


def parse_si_value(text: str) -> float:
    """Parse a numeric string with an optional SI prefix, e.g. '100k' → 100000.0."""
    text = text.strip()
    if not text:
        raise ValueError("Empty value")
    if text[-1] in _SI_PREFIXES:
        return float(text[:-1]) * _SI_PREFIXES[text[-1]]
    return float(text)


def parse_si_list(text: str) -> list:
    """Parse SI-prefixed values separated by commas and/or whitespace."""
    parts = [part for part in re.split(r"[\s,]+", text.strip()) if part]
    return [parse_si_value(part) for part in parts]


def format_si_value(value: float) -> str:
    """Format a float with the largest clean SI prefix, e.g. 1000000.0 → '1M'."""
    for suffix, mult in [('T', 1e12), ('G', 1e9), ('M', 1e6), ('k', 1e3)]:
        if value >= mult and value % mult == 0:
            return f"{value / mult:g}{suffix}"
    return f"{value:g}"


def format_si_compact_0(value: float) -> str:
    """Format value using SI suffixes with zero decimals (e.g. 15320 -> '15k')."""
    try:
        v = float(value)
    except Exception:
        return "0"
    if v == 0.0:
        return "0"

    abs_v = abs(v)
    scales = [
        (1e12, 'T'),
        (1e9, 'G'),
        (1e6, 'M'),
        (1e3, 'k'),
        (1.0, ''),
        (1e-3, 'm'),
        (1e-6, 'u'),
        (1e-9, 'n'),
        (1e-12, 'p'),
    ]
    for mult, suffix in scales:
        if abs_v >= mult:
            return f"{v / mult:.0f}{suffix}"
    # Very small values: fall back to 0 with no decimals to keep display compact.
    return "0"


class MainUI:
    def __init__(self, root):
        self.root = root
        self.config = Config('global_config.json', 'TASE_devices.csv')
        self.runner = MeasurementRunner(self.config)
        self.runner.log_callback = self._post_log
        self.runner.status_callback = self._post_status
        self.plot_bridge = PlotBridge()
        self.runner.plot = self.plot_bridge
        self.runner.contact_state_callback = lambda state: self._post(self._set_contact_state, state)
        self.runner.light_state_callback = lambda state: self._post(self._set_light_state, state)
        self._run_thread = None
        self._prober_warning_shown = False
        self.prober_available = False
        self.prober_frame = None
        self.device_selection_button = None
        # Keep CMU mode labels sourced from shared bindings metadata.
        self.cmu_mode_options = [(code, get_cmu_mode_name(code)) for code, _ in B1500_CMU_MEASUREMENT_MODES]
        # Selected devices for custom runs (device names)
        self.selected_device_names = set()

        self.root.title("Python Measurement App")
        self.root.geometry("900x900")
        for col, weight in enumerate((1, 1)):
            self.root.grid_columnconfigure(col, weight=weight)
        self.root.grid_rowconfigure(0, weight=3)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_rowconfigure(2, weight=1)

        # GUI state
        self.site_var = tk.StringVar()
        self.subsite_var = tk.StringVar()
        self.device_var = tk.StringVar()
        self.devices_csv_var = tk.StringVar()
        self.proc_var = tk.StringVar()
        self.param_vars = {}
        self._cv_calibration_store = {}
        self._cv_calib_buttons = {}
        self._cv_calibration_session_done = {}
        self._cv_phase_live_cache = {}
        self._cv_phase_probe_inflight = set()
        self._cv_phase_probe_lock = threading.Lock()
        self._cv_calib_readout_var = tk.StringVar(value="No calibration data")
        # Global ASU state
        self.asu_channels_var = tk.StringVar()
        self.asu_path_var = tk.StringVar()
        self.asu_range_var = tk.BooleanVar()
        self.status_labels = {}
        # Run options
        self.set_home_var = tk.BooleanVar(value=False)
        self.auto_separation_var = tk.BooleanVar(value=True)
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
                ('measurement_range', 'Voltage Meas Range', 'voltage_range'),
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
            'CVSweep': [
                ('gpib_address', 'GPIB Address', str),
                ('cmu_channel', 'CMU Channel', 'cmu_channel'),
                ('sweep_type', 'Sweep Type', 'cv_sweep_type'),
                ('cmu_mode', 'C-V Meas Output', 'cmu_mode'),
                ('start_bias', 'Start Bias (V)', float),
                ('stop_bias', 'Stop Bias (V)', float),
                ('points', 'Points', int),
                ('measurement_range', 'MFCMU Meas Range', 'cmu_sweep_range'),
                ('ac_level_mv', 'AC Level (mV)', float),
                ('frequencies', 'Frequencies (e.g. 100k, 1M)', str),
                ('integration_mode', 'Integration Mode', 'cmu_integration_mode'),
                ('integration_value', 'Integration (manual/PLC)', int),
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
            'WGFMU Sampling': [
                ('gpib_address', 'GPIB Address', str),
                ('channel_1', 'WGFMU Channel 1', 'wgfmu_channel'),
                ('channel_2', 'WGFMU Channel 2', 'wgfmu_channel'),
                ('force_voltage_1', 'WGFMU Force Voltage Ch1 List (V, comma-separated)', str),
                ('force_voltage_2', 'WGFMU Force Voltage Ch2 List (V, comma-separated)', str),
                ('smu_channel_list_1', 'SMU Channel List 1 (comma-separated)', str),
                ('smu_channel_list_2', 'SMU Channel List 2 (comma-separated)', str),
                ('smu_voltage_1', 'SMU Voltage List 1 (V, comma-separated)', str),
                ('smu_voltage_2', 'SMU Voltage List 2 (V, comma-separated)', str),
                ('hold_time_s', 'Hold Time Before Sampling (s)', float),
                ('sampling_rate_hz', 'Sampling Rate (Hz)', float),
                ('total_samples', 'Total Samples', int),
                ('meas_range_1', 'Current Range Ch1', 'wgfmu_current_range'),
                ('meas_range_2', 'Current Range Ch2', 'wgfmu_current_range'),
            ],
        }
        self.procedure_defaults = {
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
            'CVSweep': {
                'gpib_address': 'GPIB0::17::INSTR',
                'cmu_channel': -1,
                'sweep_type': 'single',
                'cmu_mode': 101,
                'start_bias': -2.0,
                'stop_bias': 2.0,
                'points': 101,
                'measurement_range': 0.0,
                'ac_level_mv': 30.0,
                'frequencies': '100k',
                'integration_mode': 0,
                'integration_value': 1,
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
            'WGFMU Sampling': {
                'gpib_address': 'GPIB0::17::INSTR',
                'channel_1': 101,
                'channel_2': 102,
                'force_voltage_1': '0.1',
                'force_voltage_2': '0.1',
                'smu_channel_list_1': 'SMU1',
                'smu_channel_list_2': 'SMU2',
                'smu_voltage_1': '0.0',
                'smu_voltage_2': '0.0',
                'hold_time_s': 0.0,
                'sampling_rate_hz': 1e4,
                'total_samples': 100000,
                'meas_range_1': WGFMU_MEASURE_CURRENT_RANGES[0][0],
                'meas_range_2': WGFMU_MEASURE_CURRENT_RANGES[0][0],
            },
        }

        self.build_layout()
        self._refresh_devices_csv_options()
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
        self._init_prober_state()

    def _init_prober_state(self):
        available = self.runner.prober_ctrl.initialize()
        error_message = self.runner.prober_ctrl.get_last_init_error()
        self._finish_prober_initialization(available, error_message)

    def _finish_prober_initialization(self, available: bool, error_message: str | None):
        self.prober_available = bool(available)
        self.temp_ui.set_prober_available(self.prober_available)
        self._apply_prober_availability_ui()
        if not available:
            self.position_var.set("Prober unavailable")
            if error_message:
                self.log(error_message)
            if not self._prober_warning_shown:
                self._prober_warning_shown = True
                messagebox.showwarning(
                    "SENTIO Prober Unavailable",
                    error_message or "Could not initialize the SENTIO probe station."
                )
            return

        self._init_contact_state()

    def _apply_prober_availability_ui(self):
        self._set_section_enabled(self.prober_frame, self.prober_available)
        if self.prober_frame is not None:
            title = "Prober Control" if self.prober_available else "Prober Control (Unavailable)"
            self.prober_frame.configure(text=title)
        self.set_home_check.configure(state=(tk.NORMAL if self.prober_available else tk.DISABLED))
        if self.device_selection_button is not None:
            self.device_selection_button.configure(state=(tk.NORMAL if self.prober_available else tk.DISABLED))
        if not self.prober_available:
            self.set_home_var.set(False)
            self.selected_device_names.clear()
            self._set_contact_state(False)
            self.position_var.set("Prober unavailable")
        self._update_selected_devices_label()

    def _set_section_enabled(self, section, enabled: bool):
        if section is None:
            return
        for child in section.winfo_children():
            self._set_widget_enabled(child, enabled)
            self._set_section_enabled(child, enabled)

    @staticmethod
    def _set_widget_enabled(widget, enabled: bool):
        desired = tk.NORMAL if enabled else tk.DISABLED
        try:
            widget.configure(state=desired)
            return
        except Exception:
            pass
        try:
            widget.state(["!disabled"] if enabled else ["disabled"])
        except Exception:
            pass

    def _init_contact_state(self):
        """Query prober for actual contact status and update button accordingly."""
        if not self.prober_available:
            return
        try:
            self._set_contact_state(self.runner.prober_is_in_contact())
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

        ttk.Label(self.selection_frame, text="Devices CSV").grid(row=1, column=0, sticky="w")
        csv_frame = ttk.Frame(self.selection_frame)
        csv_frame.grid(row=1, column=1, sticky="ew", pady=2)
        csv_frame.grid_columnconfigure(0, weight=1)
        self.devices_csv_cb = ttk.Combobox(csv_frame, textvariable=self.devices_csv_var)
        self.devices_csv_cb.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.devices_csv_cb.bind('<<ComboboxSelected>>', self.on_devices_csv_selected)
        ttk.Button(csv_frame, text="Browse...", command=self.browse_devices_csv).grid(row=0, column=1, sticky="ew")

        ttk.Label(self.selection_frame, text="Site").grid(row=2, column=0, sticky="w")
        self.site_cb = ttk.Combobox(self.selection_frame, textvariable=self.site_var, values=[s.name for s in self.config.sites])
        self.site_cb.grid(row=2, column=1, sticky="ew", pady=2)
        self.site_cb.bind('<<ComboboxSelected>>', self.update_subsites)

        ttk.Label(self.selection_frame, text="Subsite").grid(row=3, column=0, sticky="w")
        self.subsite_cb = ttk.Combobox(self.selection_frame, textvariable=self.subsite_var)
        self.subsite_cb.grid(row=3, column=1, sticky="ew", pady=2)
        self.subsite_cb.bind('<<ComboboxSelected>>', self.update_devices)

        ttk.Label(self.selection_frame, text="Device").grid(row=4, column=0, sticky="w")
        self.device_cb = ttk.Combobox(self.selection_frame, textvariable=self.device_var)
        self.device_cb.grid(row=4, column=1, sticky="ew", pady=2)

        ttk.Label(self.selection_frame, text="Procedure").grid(row=5, column=0, sticky="w")
        self.proc_cb = ttk.Combobox(self.selection_frame, textvariable=self.proc_var, values=list(self.procedure_fields.keys()))
        self.proc_cb.grid(row=5, column=1, sticky="ew", pady=2)
        self.proc_cb.bind('<<ComboboxSelected>>', self.on_proc_change)

        # Global ASU config
        ttk.Label(self.selection_frame, text="ASU Channels (comma)").grid(row=6, column=0, sticky="w")
        self.asu_channels_entry = ttk.Entry(self.selection_frame, textvariable=self.asu_channels_var)
        self.asu_channels_entry.grid(row=6, column=1, sticky="ew", pady=2)

        ttk.Label(self.selection_frame, text="ASU Path Mode").grid(row=7, column=0, sticky="w")
        self.asu_path_entry = ttk.Entry(self.selection_frame, textvariable=self.asu_path_var)
        self.asu_path_entry.grid(row=7, column=1, sticky="ew", pady=2)

        ttk.Label(self.selection_frame, text="ASU 1pA Range Enable").grid(row=8, column=0, sticky="w")
        self.asu_range_check = ttk.Checkbutton(self.selection_frame, variable=self.asu_range_var)
        self.asu_range_check.grid(row=8, column=1, sticky="w", pady=2)

        self.set_home_check = ttk.Checkbutton(self.selection_frame, text="Set subsite origin at start", variable=self.set_home_var)
        self.set_home_check.grid(row=9, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # Device selection button and label
        device_sel_frame = ttk.Frame(self.selection_frame)
        device_sel_frame.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        device_sel_frame.grid_columnconfigure(0, weight=1, uniform="devsel")
        device_sel_frame.grid_columnconfigure(1, weight=1, uniform="devsel")
        
        self.device_selection_button = ttk.Button(device_sel_frame, text="Device Selection...", command=self.open_device_selection)
        self.device_selection_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.selected_devices_label = ttk.Label(device_sel_frame, text="")
        self.selected_devices_label.grid(row=0, column=1, sticky="w", padx=(4, 0))

        # Action buttons
        action_frame = ttk.Frame(self.selection_frame)
        action_frame.grid(row=11, column=0, columnspan=2, sticky="ew", pady=6)
        action_frame.grid_columnconfigure(0, weight=1)
        action_frame.grid_columnconfigure(1, weight=1)
        ttk.Button(action_frame, text="Load Settings", command=self.load_settings).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(action_frame, text="Save Settings", command=self.save_settings).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self.run_button = tk.Button(self.selection_frame, text="RUN", command=self.run, bg="green", fg="white")
        self.run_button.grid(row=12, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        # Temperature controls (separate section below Selection)
        self.temp_ui.build_panel(self.selection_temp_frame)

        # Procedure settings section
        self.params_frame = ttk.LabelFrame(self.root, text="Procedure Settings")
        self.params_frame.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        self.params_frame.grid_columnconfigure(0, weight=1)
        self.params_frame.grid_columnconfigure(1, weight=1)

        # Prober controls (bottom left)
        self.prober_frame = ttk.LabelFrame(self.root, text="Prober Control")
        self.prober_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        for c in range(2):
            self.prober_frame.grid_columnconfigure(c, weight=1)

        contact_row_frame = ttk.Frame(self.prober_frame)
        contact_row_frame.grid(row=0, column=0, sticky="ew", padx=4, pady=2)
        contact_row_frame.grid_columnconfigure(0, weight=1)

        self.contact_button = tk.Button(contact_row_frame, text="CONTACT", command=self.toggle_contact, bg="yellow", fg="black")
        self.contact_button.grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=0)
        self.auto_separation_check = ttk.Checkbutton(contact_row_frame, text="", variable=self.auto_separation_var)
        self.auto_separation_check.grid(row=0, column=1, sticky="w", pady=0)
        attach_tooltip(self.auto_separation_check, "Auto Separation after measurement")

        self.light_button = tk.Button(self.prober_frame, text="Light ON", command=self.toggle_prober_light, bg="green yellow", fg="black")
        self.light_button.grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        self.go_to_device_button = ttk.Button(self.prober_frame, text="Go To Device", command=self.prober_go_to_device)
        self.go_to_device_button.grid(row=1, column=0, sticky="ew", padx=4, pady=2)
        self.set_reference_button = ttk.Button(self.prober_frame, text="Set Reference to Device", command=self.prober_set_reference)
        self.set_reference_button.grid(row=1, column=1, sticky="ew", padx=2, pady=2)
        self.read_position_button = ttk.Button(self.prober_frame, text="Read Position", command=self.read_position)
        self.read_position_button.grid(row=2, column=0, sticky="ew", padx=4, pady=2)
        ttk.Label(self.prober_frame, textvariable=self.position_var).grid(row=2, column=1, sticky="w", padx=4, pady=2)
        comp_frame = ttk.Frame(self.prober_frame)
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

    def _refresh_devices_csv_options(self):
        options = []
        if os.path.isdir(self.config.config_root):
            for name in os.listdir(self.config.config_root):
                if name.lower().endswith('.csv'):
                    options.append(os.path.normpath(os.path.join(self.config.config_root, name)))
        if self.config.devices_csv_path not in options:
            options.insert(0, self.config.devices_csv_path)
        self.devices_csv_cb['values'] = sorted(set(options), key=str.lower)
        self.devices_csv_var.set(self.config.devices_csv_path)

    def _switch_devices_csv(self, csv_path: str):
        target = (csv_path or '').strip()
        if not target:
            return
        if os.path.normcase(os.path.normpath(target)) == os.path.normcase(os.path.normpath(self.config.devices_csv_path)):
            return
        try:
            self.config.reload_devices(target, persist=True)
        except Exception as e:
            messagebox.showerror("Devices CSV", f"Failed to load devices CSV:\n{e}")
            self.devices_csv_var.set(self.config.devices_csv_path)
            self.log(f"Failed to load devices CSV '{target}': {e}")
            return
        self.selected_device_names.clear()
        self._refresh_devices_csv_options()
        self.populate_sites()
        self.log(f"Loaded devices CSV: {self.config.devices_csv_path}")

    def on_devices_csv_selected(self, event=None):
        self._switch_devices_csv(self.devices_csv_var.get())

    def browse_devices_csv(self):
        path = filedialog.askopenfilename(
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Select devices CSV",
            initialdir=self.config.config_root,
        )
        if not path:
            return
        self.devices_csv_var.set(path)
        self._switch_devices_csv(path)

    def populate_sites(self):
        site_names = [s.name for s in self.config.sites]
        self.site_cb['values'] = site_names
        if not site_names:
            self.site_var.set('')
            self.subsite_var.set('')
            self.device_var.set('')
            self.subsite_cb['values'] = []
            self.device_cb['values'] = []
            self.selected_device_names.clear()
            self._update_selected_devices_label()
            return
        current = self.site_var.get()
        self.site_var.set(current if current in site_names else site_names[0])
        self.update_subsites()

    def update_subsites(self, event=None):
        site = next((s for s in self.config.sites if s.name == self.site_var.get()), None)
        if not site:
            self.subsite_cb['values'] = []
            self.device_cb['values'] = []
            self.subsite_var.set('')
            self.device_var.set('')
            return
        subsite_names = [sub.name for sub in site.subsites]
        self.subsite_cb['values'] = subsite_names
        if not subsite_names:
            self.device_cb['values'] = []
            self.subsite_var.set('')
            self.device_var.set('')
            return
        current = self.subsite_var.get()
        self.subsite_var.set(current if current in subsite_names else subsite_names[0])
        self.update_devices()

    def update_devices(self, event=None):
        site = next((s for s in self.config.sites if s.name == self.site_var.get()), None)
        subsite = next((sub for sub in site.subsites if sub.name == self.subsite_var.get()), None) if site else None
        if not subsite:
            self.device_cb['values'] = []
            self.device_var.set('')
            return
        device_names = [d.name for d in subsite.devices]
        self.device_cb['values'] = device_names
        if device_names:
            current = self.device_var.get()
            self.device_var.set(current if current in device_names else device_names[0])
        else:
            self.device_var.set('')
        # Clear selected devices when subsite changes
        self.selected_device_names.clear()
        self._update_selected_devices_label()

    def _update_selected_devices_label(self):
        """Update the label showing how many devices are selected."""
        if not self.prober_available:
            self.selected_devices_label.config(text="Disabled (no prober)")
            return
        count = len(self.selected_device_names)
        if count == 0:
            self.selected_devices_label.config(text="")
        elif count == 1:
            self.selected_devices_label.config(text=f"✓ 1 device selected")
        else:
            self.selected_devices_label.config(text=f"✓ {count} devices selected")

    def open_device_selection(self):
        """Open the device selection dialog."""
        if not self.prober_available:
            return
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
        if self.prober_available:
            try:
                pos = self.runner.prober_read_position()
                if pos:
                    origin = self.runner.prober_ctrl.subsite_origin
                    
                    if set_home_checked and device:
                        
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
            if not self.prober_available:
                return
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
        self._cv_calib_buttons = {}

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
            elif cast == 'cmu_channel':
                label_val = self.lookup_range_label(val, B1500_CMU_CHANNELS)
                var = tk.StringVar(value=label_val)
                combo = ttk.Combobox(self.params_frame, textvariable=var, values=[label for _, label in B1500_CMU_CHANNELS], state="readonly")
                combo.grid(row=idx, column=1, sticky="ew", padx=4, pady=2)
                self.param_vars[key] = (var, cast)
            elif cast == 'cmu_mode':
                label_val = self.lookup_range_label(val, self.cmu_mode_options)
                var = tk.StringVar(value=label_val)
                combo = ttk.Combobox(self.params_frame, textvariable=var, values=[label for _, label in self.cmu_mode_options], state="readonly")
                combo.grid(row=idx, column=1, sticky="ew", padx=4, pady=2)
                self.param_vars[key] = (var, cast)
            elif cast == 'cmu_sweep_range':
                label_val = self.lookup_range_label(val, B1500_CMU_SWEEP_RANGES)
                var = tk.StringVar(value=label_val)
                combo = ttk.Combobox(self.params_frame, textvariable=var, values=[label for _, label in B1500_CMU_SWEEP_RANGES], state="readonly")
                combo.grid(row=idx, column=1, sticky="ew", padx=4, pady=2)
                self.param_vars[key] = (var, cast)
            elif cast == 'cmu_integration_mode':
                label_val = self.lookup_range_label(val, B1500_CMU_INTEGRATION_MODES)
                var = tk.StringVar(value=label_val)
                combo = ttk.Combobox(self.params_frame, textvariable=var, values=[label for _, label in B1500_CMU_INTEGRATION_MODES], state="readonly")
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
            elif cast == 'cv_sweep_type':
                label_val = next((lbl for v, lbl in CV_SWEEP_TYPES if v == val), CV_SWEEP_TYPES[0][1])
                var = tk.StringVar(value=label_val)
                combo = ttk.Combobox(self.params_frame, textvariable=var, values=[label for _, label in CV_SWEEP_TYPES], state="readonly")
                combo.grid(row=idx, column=1, sticky="ew", padx=4, pady=2)
                self.param_vars[key] = (var, cast)
            else:
                var = tk.StringVar(value=str(val))
                entry = ttk.Entry(self.params_frame, textvariable=var)
                entry.grid(row=idx, column=1, sticky="ew", padx=4, pady=2)
                self.params_frame.grid_columnconfigure(1, weight=1)
                self.param_vars[key] = (var, cast)

        # CV-specific: keep MFCMU range options consistent with entered frequency.
        if proc_name == 'CVSweep':
            self._cv_calibration_store = self.config.get_cmu_calibration()
            self._bind_cv_range_filter()
            # Bottom-anchor the calibration box: expandable spacer consumes extra height.
            spacer_row = 999
            calib_row = 1000
            self.params_frame.grid_rowconfigure(spacer_row, weight=1)
            spacer = ttk.Frame(self.params_frame)
            spacer.grid(row=spacer_row, column=0, columnspan=2, sticky="nsew")
            self._render_cv_calibration_section(calib_row)
            self._refresh_cv_calibration_readout()

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
                elif cast == 'cmu_channel':
                    settings[key] = int(self.lookup_range_value(var.get(), B1500_CMU_CHANNELS))
                elif cast == 'cmu_mode':
                    settings[key] = int(self.lookup_range_value(var.get(), self.cmu_mode_options))
                elif cast == 'cmu_sweep_range':
                    settings[key] = float(self.lookup_range_value(var.get(), B1500_CMU_SWEEP_RANGES))
                elif cast == 'cmu_integration_mode':
                    settings[key] = int(self.lookup_range_value(var.get(), B1500_CMU_INTEGRATION_MODES))
                elif cast == 'wgfmu_voltage_range':
                    settings[key] = self.lookup_range_value(var.get(), WGFMU_MEASURE_VOLTAGE_RANGES)
                elif cast == 'wgfmu_channel':
                    settings[key] = WGFMU_CHANNEL_MAP.get(var.get(), var.get())
                elif cast == 'wgfmu_current_range':
                    settings[key] = self.lookup_range_value(var.get(), WGFMU_MEASURE_CURRENT_RANGES)
                elif cast == 'cv_sweep_type':
                    settings[key] = self.lookup_range_value(var.get(), CV_SWEEP_TYPES)
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

    def _render_cv_calibration_section(self, row_idx: int):
        section = ttk.LabelFrame(self.params_frame, text="CMU Calibration")
        section.grid(row=row_idx, column=0, columnspan=2, sticky="ew", padx=4, pady=(8, 6))
        section.grid_columnconfigure(2, weight=1)

        self._cv_calib_buttons = {}
        for row, label, cal_type, tip in (
            [
                (0, "Open", "open", "Open-circuit calibration"),
                (1, "Short", "short", "Short-circuit calibration"),
                (2, "Phase", "phase", "Phase compensation"),
                (3, "Load", "load", "Load calibration"),
            ]
        ):
            btn = tk.Button(
                section,
                text=label,
                width=5,
                command=lambda c=cal_type: self._on_cv_calibration_button(c),
                bg="#f2a0a0",
                activebackground="#e38f8f",
            )
            btn.grid(row=row, column=0, sticky="ew", padx=2, pady=2)
            attach_tooltip(btn, lambda c=cal_type, t=tip: self._build_cv_calibration_tooltip(c, t))
            self._cv_calib_buttons[cal_type] = btn

        readout = ttk.Label(
            section,
            textvariable=self._cv_calib_readout_var,
            justify="left",
            anchor="w",
            wraplength=780,
        )
        readout.grid(row=0, column=2, rowspan=4, sticky="ew", padx=(10, 6), pady=4)

        cmu_item = self.param_vars.get('cmu_channel')
        if cmu_item:
            cmu_var, _ = cmu_item
            try:
                cmu_var.trace_add('write', lambda *_: self._refresh_cv_calibration_readout())
            except Exception:
                pass

        # Recompute calibration coverage state when selected frequencies change.
        freq_item = self.param_vars.get('frequencies')
        if freq_item:
            freq_var, _ = freq_item
            try:
                freq_var.trace_add('write', lambda *_: self._refresh_cv_calibration_readout())
            except Exception:
                pass

    def _build_cv_calibration_tooltip(self, cal_type: str, base_tip: str) -> str:
        try:
            cmu_var, _ = self.param_vars.get('cmu_channel', (None, None))
            if cmu_var is None:
                return base_tip
            channel = int(self.lookup_range_value(cmu_var.get(), B1500_CMU_CHANNELS))
        except Exception:
            return base_tip

        ch_data = self._cv_calibration_store.get(str(channel), {})
        entry = ch_data.get(cal_type)
        if not isinstance(entry, dict):
            return f"{base_tip}\nLast: not calibrated"

        ts = entry.get('timestamp', 'n/a')
        lines = [base_tip, f"Last: {ts}"]

        if cal_type == 'phase':
            result = entry.get('result', {}) if isinstance(entry, dict) else {}
            live = self._get_live_phase_calibrated(channel, schedule_probe=True)
            if live is True:
                lines.append("Live: calibrated")
            elif live is False:
                lines.append("Live: not calibrated")
            return "\n".join(lines)

        by_freq = entry.get('results_by_frequency', {})
        if isinstance(by_freq, dict) and by_freq:
            freq_labels = []
            for fk in by_freq.keys():
                try:
                    freq_labels.append(f"{format_si_value(float(fk))}Hz")
                except Exception:
                    pass
            if freq_labels:
                lines.append("F: " + ", ".join(sorted(freq_labels)))
            return "\n".join(lines)

        freq_hz = entry.get('frequency_hz')
        if freq_hz is not None:
            try:
                lines.append(f"F: {format_si_value(float(freq_hz))}Hz")
            except Exception:
                pass
        return "\n".join(lines)

    def _update_cv_calibration_button_colors(self):
        cmu_item = self.param_vars.get('cmu_channel')
        channel_key = None
        channel = None
        selected_freq_keys = set()
        if cmu_item:
            cmu_var, _ = cmu_item
            try:
                channel = int(self.lookup_range_value(cmu_var.get(), B1500_CMU_CHANNELS))
                if channel != -1:
                    channel_key = str(channel)
            except Exception:
                channel_key = None

        try:
            _, freqs = self._get_cv_channel_and_frequencies()
            selected_freq_keys = {self._freq_key(f) for f in freqs}
        except Exception:
            selected_freq_keys = set()

        session_done = self._cv_calibration_session_done.get(channel_key, {}) if channel_key else {}
        stored = self._cv_calibration_store.get(channel_key, {}) if channel_key else {}

        for cal_type, btn in self._cv_calib_buttons.items():
            if cal_type == 'phase':
                phase_done_session = bool(session_done.get('phase', False))
                phase_live_calibrated = self._get_live_phase_calibrated(channel) if channel_key else None
                phase_has_stored = cal_type in stored
                if phase_done_session:
                    btn.configure(bg="#9be39b", activebackground="#87d287")
                elif phase_live_calibrated is True:
                    btn.configure(bg="#f3e58f", activebackground="#e7d97f")
                elif phase_live_calibrated is False:
                    btn.configure(bg="#f2a0a0", activebackground="#e38f8f")
                elif phase_has_stored:
                    btn.configure(bg="#f3e58f", activebackground="#e7d97f")
                else:
                    btn.configure(bg="#f2a0a0", activebackground="#e38f8f")
                continue

            session_freqs = set(session_done.get(cal_type, set()))
            stored_freqs = self._get_stored_freq_keys(stored.get(cal_type))

            if selected_freq_keys and selected_freq_keys.issubset(session_freqs):
                btn.configure(bg="#9be39b", activebackground="#87d287")
            elif selected_freq_keys and selected_freq_keys.issubset(stored_freqs):
                btn.configure(bg="#f3e58f", activebackground="#e7d97f")
            else:
                btn.configure(bg="#f2a0a0", activebackground="#e38f8f")

    def _get_live_phase_calibrated(self, channel: int | None, schedule_probe: bool = False):
        """Return cached phase-comp state; optional async probe when explicitly requested.

        Important: ADJ? can trigger MFCMU activity, so we do NOT probe by default
        during normal UI refresh paths (like procedure selection).
        """
        if channel is None or channel == -1:
            return None

        channel_key = str(channel)
        now = time.time()
        cached = self._cv_phase_live_cache.get(channel_key)
        if cached and (now - cached.get('ts', 0.0) < 2.0):
            return cached.get('calibrated')

        # Avoid extra instrument traffic while a run/calibration is active.
        if self._run_thread and self._run_thread.is_alive():
            return cached.get('calibrated') if cached else None

        if schedule_probe:
            self._schedule_live_phase_probe(channel)
        return cached.get('calibrated') if cached else None

    def _schedule_live_phase_probe(self, channel: int):
        channel_key = str(channel)
        with self._cv_phase_probe_lock:
            if channel_key in self._cv_phase_probe_inflight:
                return
            self._cv_phase_probe_inflight.add(channel_key)

        def worker():
            calibrated = None
            try:
                settings_now = self.collect_settings()
                gpib_address = settings_now.get('gpib_address', 'GPIB0::17::INSTR')
                b1500 = self.runner.get_b1500(gpib_address)
                result_code = b1500.get_cmu_phase_compensation_result(channel, mode=0)
                # ADJ? result meanings: 0=ok, 1=failed, 2=aborted, 3=never performed.
                calibrated = result_code != 3
            except Exception:
                calibrated = None
            finally:
                self._post(self._finish_live_phase_probe, channel_key, calibrated)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_live_phase_probe(self, channel_key: str, calibrated):
        self._cv_phase_live_cache[channel_key] = {
            'ts': time.time(),
            'calibrated': calibrated,
        }
        with self._cv_phase_probe_lock:
            self._cv_phase_probe_inflight.discard(channel_key)

        # Repaint colors/readout with fresh live state.
        self._refresh_cv_calibration_readout()

    @staticmethod
    def _freq_key(freq_hz: float) -> str:
        return f"{float(freq_hz):.12g}"

    def _get_stored_freq_keys(self, entry) -> set:
        if not isinstance(entry, dict):
            return set()
        # New format: explicit map of per-frequency results.
        by_freq = entry.get('results_by_frequency', {})
        if isinstance(by_freq, dict) and by_freq:
            return set(str(k) for k in by_freq.keys())
        # Legacy format: single frequency_hz field.
        freq = entry.get('frequency_hz', None)
        if freq is None:
            return set()
        try:
            return {self._freq_key(float(freq))}
        except Exception:
            return set()

    def _get_cv_channel_and_frequencies(self):
        cmu_item = self.param_vars.get('cmu_channel')
        if not cmu_item:
            raise RuntimeError("CMU channel field not available.")
        cmu_var, _ = cmu_item
        channel = int(self.lookup_range_value(cmu_var.get(), B1500_CMU_CHANNELS))
        if channel == -1:
            raise ValueError("Select a valid CMU Channel before calibration.")

        freq_item = self.param_vars.get('frequencies')
        if not freq_item:
            raise RuntimeError("Frequency field not available.")
        freq_var, _ = freq_item
        raw = str(freq_var.get()).strip()
        if not raw:
            raise ValueError("Enter at least one frequency before calibration.")
        frequencies_hz = sorted(float(f) for f in parse_si_list(raw))
        if not frequencies_hz:
            raise ValueError("Enter at least one frequency before calibration.")
        return channel, frequencies_hz

    def _set_cv_calibration_buttons_enabled(self, enabled: bool):
        state = tk.NORMAL if enabled else tk.DISABLED
        for btn in self._cv_calib_buttons.values():
            try:
                btn.configure(state=state)
            except Exception:
                pass

    def _get_cmu_channel_name(self, channel: int) -> str:
        try:
            return self.lookup_range_label(channel, B1500_CMU_CHANNELS)
        except Exception:
            return str(channel)

    def _commit_cv_calibration_result(self, channel: int, cal_type: str, result, frequencies_hz=None):
        channel_key = str(channel)
        channel_store = self._cv_calibration_store.setdefault(channel_key, {})
        if cal_type == 'phase':
            entry = {
                'timestamp': datetime.now().isoformat(timespec='seconds'),
                'result': result,
            }
        else:
            entry = {
                'timestamp': datetime.now().isoformat(timespec='seconds'),
                'frequencies_hz': list(frequencies_hz or []),
                'results_by_frequency': result,
            }
        channel_store[cal_type] = entry

        session_state = self._cv_calibration_session_done.setdefault(channel_key, {})
        if cal_type == 'phase':
            session_state['phase'] = True
        else:
            done_set = set(session_state.get(cal_type, set()))
            done_set.update(self._freq_key(f) for f in (frequencies_hz or []))
            session_state[cal_type] = done_set

        self.config.set_cmu_calibration(self._cv_calibration_store)
        self.config.set_procedure_settings('CVSweep', self.collect_settings())
        self._refresh_cv_calibration_readout()

    def _finish_cv_calibration_thread(self):
        self.runner.stop_event.clear()
        self._run_thread = None
        self._set_running_state(False)
        self._set_cv_calibration_buttons_enabled(True)

    def _on_cv_calibration_button(self, cal_type: str):
        if self._run_thread and self._run_thread.is_alive():
            messagebox.showwarning("Calibration busy", "A run is in progress. Stop the run before calibrating.")
            return

        try:
            channel, frequencies_hz = self._get_cv_channel_and_frequencies()
            settings_now = self.collect_settings()
            gpib_address = settings_now.get('gpib_address', 'GPIB0::17::INSTR')
            ac_level_v = float(settings_now.get('ac_level_mv', 30.0)) / 1000.0
        except Exception as e:
            messagebox.showerror("Calibration setup", str(e))
            return

        prompts = {
            'open': "Prepare OPEN condition at the fixture, then press OK to start.",
            'short': "Prepare SHORT condition at the fixture, then press OK to start.",
            'phase': "Open measurement terminal (OPEN condition), then press OK to start phase compensation.",
            'load': "Connect LOAD standard, then press OK to start.",
        }
        if not messagebox.askokcancel("CMU Calibration", prompts.get(cal_type, "Start calibration?")):
            return

        self._set_cv_calibration_buttons_enabled(False)
        self._cv_calib_readout_var.set("Calibration running")
        self.root.update_idletasks()
        self.runner.stop_event.clear()
        self._set_running_state(True)
        channel_name = self._get_cmu_channel_name(channel)

        def target():
            try:
                self.runner.check_stop("Stop requested before CMU calibration start")
                self._post_log(f"Calibration running on {channel_name}")

                b1500 = self.runner.get_b1500(gpib_address)
                b1500.set_timeout(120000)
                b1500.enable_error_detect(True)
                b1500.set_switch(B1500_CH_ALL, False)
                b1500.set_switch(channel, True)
                b1500.force_cmu_ac_level(channel, ac_level_v)

                if cal_type == 'phase':
                    self.runner.check_stop("Stop requested before phase compensation")
                    result = b1500.run_cmu_phase_compensation(channel)
                    self._post(self._commit_cv_calibration_result, channel, cal_type, result, None)
                    self._post_log(f"CMU {cal_type} calibration completed on {channel_name}")
                else:
                    result = {}
                    for freq in frequencies_hz:
                        self.runner.check_stop("Stop requested during CMU calibration")
                        freq_key = self._freq_key(freq)
                        result[freq_key] = b1500.run_cmu_correction(channel, cal_type, freq)
                    self._post(self._commit_cv_calibration_result, channel, cal_type, result, list(frequencies_hz))
                    freq_labels = ", ".join(f"{format_si_value(f)}Hz" for f in frequencies_hz)
                    self._post_log(f"CMU {cal_type} calibration completed on {channel_name} @ [{freq_labels}]")
            except MeasurementAbortRequested:
                self._post_log(f"CMU {cal_type} calibration aborted by user.")
                self._post(self._cv_calib_readout_var.set, "Calibration aborted.")
                self._post(self._refresh_cv_calibration_readout)
            except Exception as e:
                self._post_log(f"CMU {cal_type} calibration error details: {e}")
                self._post(self._refresh_cv_calibration_readout)
                self._post(messagebox.showerror, "Calibration failed", str(e))
                self._post_log(f"CMU {cal_type} calibration failed: {e}")
            finally:
                self._post(self._finish_cv_calibration_thread)

        self._run_thread = threading.Thread(target=target, daemon=True)
        self._run_thread.start()

    def _refresh_cv_calibration_readout(self):
        cmu_item = self.param_vars.get('cmu_channel')
        if not cmu_item:
            self._cv_calib_readout_var.set("No calibration data")
            self._update_cv_calibration_button_colors()
            return

        cmu_var, _ = cmu_item
        try:
            channel = int(self.lookup_range_value(cmu_var.get(), B1500_CMU_CHANNELS))
        except Exception:
            self._cv_calib_readout_var.set("No calibration data")
            self._update_cv_calibration_button_colors()
            return

        ch_data = self._cv_calibration_store.get(str(channel), {})
        channel_name = self._get_cmu_channel_name(channel)
        lines = [f"{channel_name}"]

        # Keep selected frequencies for table columns, but don't render a
        # separate frequency summary line in the main readout.
        try:
            _, selected_freqs_hz = self._get_cv_channel_and_frequencies()
        except Exception:
            selected_freqs_hz = []

        # Compact per-frequency coefficient table.
        # Only populate the pair that corresponds to the calibration actually run:
        # open -> Ro/Xo, short -> Rs/Xs, load -> Rl/Xl.
        coeff_by_freq = {}
        for cal_key in ("open", "short", "load"):
            entry = ch_data.get(cal_key)
            if not isinstance(entry, dict):
                continue

            def _merge_coeff_for_type(freq_hz: float, coeffs: dict):
                row = coeff_by_freq.setdefault(
                    freq_hz,
                    {"Go": None, "Bo": None, "Rs": None, "Xs": None, "Rl": None, "Xl": None},
                )
                if cal_key == "open":
                    row["Go"] = float(coeffs.get('open_r', 0.0))
                    row["Bo"] = float(coeffs.get('open_i', 0.0))
                elif cal_key == "short":
                    row["Rs"] = float(coeffs.get('short_r', 0.0))
                    row["Xs"] = float(coeffs.get('short_i', 0.0))
                else:
                    row["Rl"] = float(coeffs.get('load_r', 0.0))
                    row["Xl"] = float(coeffs.get('load_i', 0.0))

            by_freq = entry.get('results_by_frequency', {})
            if isinstance(by_freq, dict) and by_freq:
                for freq_key, item in by_freq.items():
                    if not isinstance(item, dict):
                        continue
                    coeffs = item.get('coefficients', {})
                    if not isinstance(coeffs, dict):
                        continue
                    try:
                        freq_hz = float(freq_key)
                    except Exception:
                        continue
                    _merge_coeff_for_type(freq_hz, coeffs)
            else:
                # Legacy single-frequency storage.
                result = entry.get('result', {})
                coeffs = result.get('coefficients', {}) if isinstance(result, dict) else {}
                if isinstance(coeffs, dict):
                    try:
                        legacy_freq = entry.get('frequency_hz')
                        if legacy_freq is None:
                            raise ValueError("missing frequency_hz")
                        freq_hz = float(legacy_freq)
                    except Exception:
                        freq_hz = None
                    if freq_hz is not None:
                        _merge_coeff_for_type(freq_hz, coeffs)

        # Table columns should follow currently selected frequencies. If none are
        # available (e.g. invalid frequency field), fall back to stored frequencies.
        table_freqs = [float(f) for f in selected_freqs_hz] if selected_freqs_hz else sorted(coeff_by_freq.keys())
        # Ensure selected frequencies appear even if not calibrated yet.
        for f in table_freqs:
            coeff_by_freq.setdefault(
                float(f),
                {"Go": None, "Bo": None, "Rs": None, "Xs": None, "Rl": None, "Xl": None},
            )

        if table_freqs:
            sorted_freqs = [float(f) for f in table_freqs]

            def _fmt(v):
                return "-" if v is None else format_si_compact_0(v)

            lines.extend([
                "",
                "param\t" + "\t".join(format_si_compact_0(f) for f in sorted_freqs),
            ])
            for param in ("Go", "Bo", "Rs", "Xs", "Rl", "Xl"):
                row_vals = [_fmt(coeff_by_freq[f][param]) for f in sorted_freqs]
                lines.append(param + "\t" + "\t".join(row_vals))

        self._cv_calib_readout_var.set("\n".join(lines))
        self._update_cv_calibration_button_colors()

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
                loaded_data = json.load(f)
                current_devices_csv = self.config.devices_csv_path
                self.config.replace_data(loaded_data)
                self.config.data['devices_csv_path'] = current_devices_csv
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
            messagebox.showerror("Missing Chip ID", "Please enter a Chip ID before running.")
            return
        site = next((s for s in self.config.sites if s.name == self.site_var.get()), None)
        if site is None:
            self.log("Select a valid site before running.")
            return
        subsite = next((sub for sub in site.subsites if sub.name == self.subsite_var.get()), None)
        if subsite is None:
            self.log("Select a valid subsite before running.")
            return
        device = next((d for d in subsite.devices if d.name == self.device_var.get()), None)
        if device is None:
            self.log("Select a valid device before running.")
            return
        temp_info = self.temp_ui.collect_run_inputs()
        if temp_info is None:
            return
        temp_enabled, temp_list, wait_after, temp_mode = temp_info
        if temp_enabled and not self.prober_available:
            messagebox.showerror("Temperature", "Temperature control requires a connected prober.")
            return

        proc_class = {
            'FourTerminalIV': FourTerminalIVProcedure,
            'OxideBreakdown': OxideBreakdownProcedure,
            'CVSweep': CVSweepProcedure,
            'PUND': PUNDProcedure,
            'PUNDFatigue': PUNDFatigueProcedure,
            'WGFMU Sampling': WGFMUSamplingProcedure,
        }[proc_name]
        settings = self.collect_settings()
        # Cache current settings/selection in memory only to avoid overwriting config files on run
        self.config.data.setdefault('procedures', {})[proc_name] = settings
        self.config.data['last_selection'] = self.build_last_selection()
        set_home = self.set_home_var.get()
        self.runner.auto_separation_after_measurement = bool(self.auto_separation_var.get())
        
        # Determine which devices to run (always a list)
        if self.prober_available and self.selected_device_names:
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
            if set_home:
                if self.prober_available:
                    self._post_log(f"Setting subsite origin to device '{device.name}' at ({device.x}um, {device.y}um).")
                    self.runner.set_subsite_origin(device.x, device.y)
                else:
                    self._post_log("No prober connected: skipping subsite origin setup.")
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
                if self.prober_available:
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
        if not self.prober_available:
            return
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
        if not self.prober_available:
            return
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
        if not self.prober_available:
            return
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
        if not self.prober_available:
            self.position_var.set("Prober unavailable")
            return
        try:
            x, y = self.runner.prober_read_position()
            self.position_var.set(f"X={x:.1f}um , Y={y:.1f}um")
        except Exception:
            self.position_var.set("X=-- , Y=--")

    def toggle_prober_light(self):
        if not self.prober_available:
            return
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
        if ch is None or ch == B1500_CH_NOCH:
            ch_label = "N/A"
        elif ch == B1500_CH_ALL:
            ch_label = "ALL"
        else:
            ch_label = self.lookup_smu_label(ch)
        dt_desc = describe_data_type_short(dt) if dt is not None else "T?"
        label = f"{ch_label} {dt_desc} 0x{status:X}"
        tooltip_type = describe_data_type(dt) if dt is not None else "Type ?"
        tooltip = f"{ch_label} | {tooltip_type} | {desc} (0x{status:X})"
        return label, tooltip

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

    def _bind_cv_range_filter(self):
        """Filter CMU range options based on frequency limits from the MFCMU table."""
        range_item = self.param_vars.get('measurement_range')
        freq_item = self.param_vars.get('frequencies')
        if not range_item or not freq_item:
            return
        range_var, _ = range_item
        freq_var, _ = freq_item

        def refresh(*_args):
            try:
                first_freq = parse_si_value(str(freq_var.get()).split(',')[0])
            except Exception:
                first_freq = 100000.0
            opts = self._cv_range_options_for_freq(first_freq)
            combo = None
            for child in self.params_frame.winfo_children():
                if isinstance(child, ttk.Combobox) and child.cget('textvariable') == str(range_var):
                    combo = child
                    break
            if combo is None:
                return
            labels = [label for _, label in opts]
            combo.configure(values=labels)
            if range_var.get() not in labels:
                range_var.set(labels[0])

        # Initial sync and live updates as frequency is edited.
        refresh()
        try:
            freq_var.trace_add('write', refresh)
        except Exception:
            pass

    def _cv_range_options_for_freq(self, freq_text):
        # Frequency-dependent availability from MFCMU table:
        # <=200 kHz: all manual ranges; <=2 MHz: up to 30 kOhm; <=5 MHz: up to 3 kOhm.
        try:
            freq = float(freq_text)
        except Exception:
            return B1500_CMU_SWEEP_RANGES

        limits = {
            50.0: 5e6,
            100.0: 5e6,
            300.0: 5e6,
            1000.0: 5e6,
            3000.0: 5e6,
            10000.0: 2e6,
            30000.0: 2e6,
            100000.0: 2e5,
            300001.0: 2e5,
        }

        filtered = [B1500_CMU_SWEEP_RANGES[0]]  # Auto ranging always available
        for val, label in B1500_CMU_SWEEP_RANGES[1:]:
            max_freq = limits.get(float(val), 0.0)
            if freq <= max_freq:
                filtered.append((val, label))
        return filtered

    # Temperature UI logic is encapsulated in TemperatureUI (ui_temperature.py)
    def _on_close(self):
        self.root.withdraw()
        self.temp_ui.stop_run()
        self.runner.safe_stop()
        if self._run_thread and self._run_thread.is_alive():
            self._run_thread.join(timeout=10)
        self.plot_bridge.shutdown()
        self.root.destroy()

    def apply_last_selection(self, last_sel):
        if last_sel.get('procedure'):
            self.proc_var.set(last_sel['procedure'])
            self.proc_cb.set(last_sel['procedure'])
            self.render_param_form(last_sel['procedure'])
        site_names = [s.name for s in self.config.sites]
        if site_names:
            preferred_site = last_sel.get('site')
            self.site_var.set(preferred_site if preferred_site in site_names else site_names[0])
            self.update_subsites()
            selected_site = next((s for s in self.config.sites if s.name == self.site_var.get()), None)
            if selected_site and selected_site.subsites:
                sub_names = [sub.name for sub in selected_site.subsites]
                preferred_sub = last_sel.get('subsite')
                self.subsite_var.set(preferred_sub if preferred_sub in sub_names else sub_names[0])
                self.update_devices()
                selected_sub = next((sub for sub in selected_site.subsites if sub.name == self.subsite_var.get()), None)
                if selected_sub and selected_sub.devices:
                    dev_names = [d.name for d in selected_sub.devices]
                    preferred_dev = last_sel.get('device')
                    self.device_var.set(preferred_dev if preferred_dev in dev_names else dev_names[0])
        if 'set_home_before_run' in last_sel:
            self.set_home_var.set(bool(last_sel['set_home_before_run']))
        if 'auto_separation_after_measurement' in last_sel:
            self.auto_separation_var.set(bool(last_sel['auto_separation_after_measurement']))
        if 'chip' in last_sel:
            self.chip_var.set(last_sel['chip'])
        if 'selected_devices' in last_sel:
            self.selected_device_names = set(last_sel['selected_devices'])
            self._update_selected_devices_label()
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
            'auto_separation_after_measurement': self.auto_separation_var.get(),
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
