"""Parsing helpers for SCPI/B1500 text payloads."""

import re

from .codes import SCPI_STATUS_MAP

_FMT5_ITEM_RE = re.compile(r"^([A-Za-z])([A-Za-z0-9])([A-Za-z])([+-]?[0-9]*\.?[0-9]+E[+-][0-9]{2})$")


def parse_fmt5_item(item: str) -> tuple[str, str, str, float]:
    token = item.strip().rstrip(",")
    match = _FMT5_ITEM_RE.match(token)
    if not match:
        raise ValueError(f"Invalid FMT5 token: {item!r}")
    status, channel, data_type, value_text = match.groups()
    return status, channel, data_type, float(value_text)


def parse_scpi_status(item: str) -> int:
    return SCPI_STATUS_MAP.get(item[0], 0)


def parse_csv_floats(text: str) -> list[float]:
    vals: list[float] = []
    for token in text.strip().split(","):
        token = token.strip()
        if not token:
            continue
        vals.append(float(token))
    return vals


__all__ = ["parse_fmt5_item", "parse_scpi_status", "parse_csv_floats"]