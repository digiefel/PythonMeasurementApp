"""Shared constant tables and pure metadata for instrument bindings."""

from .parsers import parse_csv_floats, parse_fmt5_item, parse_scpi_status

# Hardware channel helpers
DEFAULT_SMU_CHANNEL_MAP = {
    "SMU1": 3,
    "SMU2": 4,
    "SMU3": 5,
    "SMU4": 6,
}

SMU_CHANNEL_MAP = dict(DEFAULT_SMU_CHANNEL_MAP)

DEFAULT_WGFMU_CHANNEL_MAP = {
    "WGFMU1:RS": 101,
    "WGFMU2:RS": 102,
    "WGFMU3:RS": 201,
    "WGFMU4:RS": 202,
}

WGFMU_CHANNEL_MAP = dict(DEFAULT_WGFMU_CHANNEL_MAP)

WGFMU_SLOT_MAP = {
    101: 1,
    102: 102,
    201: 2,
    202: 202,
}


def apply_smu_channel_map(channel_map):
    """Replace the process-wide SMU label map in-place.

    UI/procedure modules import ``SMU_CHANNEL_MAP`` directly, so this must keep
    the original dict object alive and mutate its contents.
    """
    normalized = {}
    for label, channel in (channel_map or {}).items():
        label_text = str(label).strip()
        if not label_text:
            continue
        normalized[label_text] = int(float(channel))
    if not normalized:
        return
    SMU_CHANNEL_MAP.clear()
    SMU_CHANNEL_MAP.update(normalized)


def reset_smu_channel_map():
    apply_smu_channel_map(DEFAULT_SMU_CHANNEL_MAP)

# Range presets (from agb1500.h: positive = limited auto, negative = fixed, 0 = auto)
B1500_VOLTAGE_RANGES = [
    (0.0, "Auto"),
    (0.5, "Auto (≥0.5 V)"),
    (2.0, "Auto (≥2 V)"),
    (5.0, "Auto (≥5 V)"),
    (20.0, "Auto (≥20 V)"),
    (40.0, "Auto (≥40 V)"),
    (100.0, "Auto (≥100 V)"),
    (200.0, "Auto (≥200 V)"),
    (-0.5, "Fixed 0.5 V"),
    (-2.0, "Fixed 2 V"),
    (-5.0, "Fixed 5 V"),
    (-20.0, "Fixed 20 V"),
    (-40.0, "Fixed 40 V"),
    (-100.0, "Fixed 100 V"),
    (-200.0, "Fixed 200 V"),
]

B1500_CURRENT_RANGES = [
    (0.0, "Auto"),
    (1.0e-12, "Auto (≥1 pA)"),
    (1.0e-11, "Auto (≥10 pA)"),
    (1.0e-10, "Auto (≥100 pA)"),
    (1.0e-9, "Auto (≥1 nA)"),
    (10.0e-9, "Auto (≥10 nA)"),
    (100.0e-9, "Auto (≥100 nA)"),
    (1.0e-6, "Auto (≥1 µA)"),
    (10.0e-6, "Auto (≥10 µA)"),
    (100.0e-6, "Auto (≥100 µA)"),
    (1.0e-3, "Auto (≥1 mA)"),
    (10.0e-3, "Auto (≥10 mA)"),
    (100.0e-3, "Auto (≥100 mA)"),
    (1.0, "Auto (≥1 A)"),
    (-1.0e-12, "Fixed 1 pA"),
    (-1.0e-11, "Fixed 10 pA"),
    (-1.0e-10, "Fixed 100 pA"),
    (-1.0e-9, "Fixed 1 nA"),
    (-10.0e-9, "Fixed 10 nA"),
    (-100.0e-9, "Fixed 100 nA"),
    (-1.0e-6, "Fixed 1 µA"),
    (-10.0e-6, "Fixed 10 µA"),
    (-100.0e-6, "Fixed 100 µA"),
    (-1.0e-3, "Fixed 1 mA"),
    (-10.0e-3, "Fixed 10 mA"),
    (-100.0e-3, "Fixed 100 mA"),
    (-1.0, "Fixed 1 A"),
]

# CMU/C-V helper option lists for UI usage.
B1500_CMU_CHANNELS = [
    (7, "Default CMU"),
]

# Full MFCMU measurement mode list from the B1500 programming guide.
B1500_CMU_MEASUREMENT_MODES_ALL = [
    (1, "R-X"),
    (2, "G-B"),
    (10, "Z-Theta (radian)"),
    (11, "Z-Theta (degree)"),
    (20, "Y-Theta (radian)"),
    (21, "Y-Theta (degree)"),
    (100, "Cp-G"),
    (101, "Cp-D"),
    (102, "Cp-Q"),
    (103, "Cp-Rp"),
    (200, "Cs-Rs"),
    (201, "Cs-D"),
    (202, "Cs-Q"),
    (300, "Lp-G"),
    (301, "Lp-D"),
    (302, "Lp-Q"),
    (303, "Lp-Rp"),
    (400, "Ls-Rs"),
    (401, "Ls-D"),
    (402, "Ls-Q"),
]

B1500_CMU_MODE_NAME_BY_CODE = {code: label for code, label in B1500_CMU_MEASUREMENT_MODES_ALL}

# Split each CMU mode into primary/monitor quantity names used by sweepCv output.
B1500_CMU_MODE_COMPONENTS = {
    1: ("R", "X"),
    2: ("G", "B"),
    10: ("Z", "Theta_rad"),
    11: ("Z", "Theta_deg"),
    20: ("Y", "Theta_rad"),
    21: ("Y", "Theta_deg"),
    100: ("Cp", "G"),
    101: ("Cp", "D"),
    102: ("Cp", "Q"),
    103: ("Cp", "Rp"),
    200: ("Cs", "Rs"),
    201: ("Cs", "D"),
    202: ("Cs", "Q"),
    300: ("Lp", "G"),
    301: ("Lp", "D"),
    302: ("Lp", "Q"),
    303: ("Lp", "Rp"),
    400: ("Ls", "Rs"),
    401: ("Ls", "D"),
    402: ("Ls", "Q"),
}

B1500_CMU_COMPONENT_UNITS = {
    "R": "Ohm",
    "X": "Ohm",
    "Z": "Ohm",
    "Y": "S",
    "G": "S",
    "B": "S",
    "Cp": "F",
    "Cs": "F",
    "Lp": "H",
    "Ls": "H",
    "Rp": "Ohm",
    "Rs": "Ohm",
    "D": "",
    "Q": "",
    "Theta_rad": "rad",
    "Theta_deg": "deg",
}

# Curated subset shown in the UI by default.
B1500_CMU_MEASUREMENT_MODES = [
    (100, "Cp-G"),
    (103, "Cp-Rp"),
    (200, "Cs-Rs"),
    (11, "Z-Theta (degree)"),
]

B1500_CMU_INTEGRATION_MODES = [
    (0, "Auto"),
    (1, "Manual"),
    (2, "PLC"),
]

# MFCMU measurement range argument for sweepCv/spotCmuMeas.
# Values are representative inputs for each documented range bucket.
B1500_CMU_SWEEP_RANGES = [
    (0.0, "Auto ranging"),
    (50.0, "50 Ohm"),
    (100.0, "100 Ohm"),
    (300.0, "300 Ohm"),
    (1000.0, "1 kOhm"),
    (3000.0, "3 kOhm"),
    (10000.0, "10 kOhm"),
    (30000.0, "30 kOhm"),
    (100000.0, "100 kOhm"),
    (300001.0, "300 kOhm"),
]

WGFMU_FORCE_VOLTAGE_RANGES = [
    (3000, "Auto"),
    (3001, "3 V"),
    (3002, "5 V"),
    (3003, "10 V Negative"),
    (3004, "10 V Positive"),
]

WGFMU_MEASURE_VOLTAGE_RANGES = [
    (5001, "5 V"),
    (5002, "10 V"),
]

WGFMU_MEASURE_CURRENT_RANGES = [
    (6001, "1 µA"),
    (6002, "10 µA"),
    (6003, "100 µA"),
    (6004, "1 mA"),
    (6005, "10 mA"),
]
