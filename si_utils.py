import math
import re


_SI_PREFIXES = {
    'T': 1e12, 'G': 1e9, 'M': 1e6, 'k': 1e3, 'K': 1e3,
    'm': 1e-3, 'u': 1e-6, '\u03bc': 1e-6, 'n': 1e-9, 'p': 1e-12,
}


def parse_si_value(text: str) -> float:
    """Parse a numeric string with an optional SI prefix, e.g. '100k' -> 100000.0."""
    text = text.strip()
    if not text:
        raise ValueError("Empty value")
    if text[-1] in _SI_PREFIXES:
        return float(text[:-1]) * _SI_PREFIXES[text[-1]]
    return float(text)


def parse_si_list(text: str) -> list[float]:
    """Parse SI-prefixed values separated by commas and/or whitespace."""
    parts = [part for part in re.split(r"[\s,]+", text.strip()) if part]
    return [parse_si_value(part) for part in parts]


def format_si_value(value: float) -> str:
    """Format a float with the largest clean SI prefix, e.g. 1000000.0 -> '1M'."""
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
    return "0"


def format_si_compact(value: float, sig_figs: int = 3) -> str:
    """Format value using SI suffixes with compact significant figures."""
    try:
        v = float(value)
    except Exception:
        return "0"

    if math.isnan(v):
        return "nan"
    if math.isinf(v):
        return "inf" if v > 0 else "-inf"
    if v == 0.0:
        return "0"

    digits = max(int(sig_figs), 1)
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
            return f"{v / mult:.{digits}g}{suffix}"

    smallest_mult, smallest_suffix = scales[-1]
    return f"{v / smallest_mult:.{digits}g}{smallest_suffix}"
