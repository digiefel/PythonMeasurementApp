"""Human-readable description helpers for instrument values and modes."""

from .codes import B1500_DATA_TYPE_SHORT, B1500_DATA_TYPE_TEXT, B1500_STATUS_BIT_TEXT
from .constants import (
    B1500_CMU_COMPONENT_UNITS,
    B1500_CMU_MODE_COMPONENTS,
    B1500_CMU_MODE_NAME_BY_CODE,
)


def describe_status_bits(status: int) -> str:
    if not status:
        return "OK"
    parts = [text for bit, text in B1500_STATUS_BIT_TEXT.items() if status & bit]
    if not parts:
        return f"0x{status:X} (unknown bits)"
    return "; ".join(parts)


def describe_data_type(data_type: int) -> str:
    return B1500_DATA_TYPE_TEXT.get(data_type, f"Type {data_type}")


def describe_data_type_short(data_type: int) -> str:
    return B1500_DATA_TYPE_SHORT.get(data_type, f"T{data_type}")


def get_cmu_mode_name(mode: int) -> str:
    return B1500_CMU_MODE_NAME_BY_CODE.get(mode, f"Mode {mode}")


def get_cmu_mode_components(mode: int) -> tuple[str, str]:
    return B1500_CMU_MODE_COMPONENTS.get(mode, ("Primary", "Monitor"))


def format_cmu_component_label(component: str) -> str:
    unit = B1500_CMU_COMPONENT_UNITS.get(component, "")
    return f"{component} ({unit})" if unit else component


__all__ = [
    "describe_status_bits",
    "describe_data_type",
    "describe_data_type_short",
    "get_cmu_mode_name",
    "get_cmu_mode_components",
    "format_cmu_component_label",
]