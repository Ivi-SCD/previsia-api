"""Shared parsing utilities used by notebooks and API."""

import re

_CURRENCY_RE = re.compile(r"R\$\s*")


def parse_brl(value) -> float:
    """Convert Brazilian currency string (e.g. 'R$ 25.007,89' or '4295.12') to float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = _CURRENCY_RE.sub("", str(value)).strip()
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    return float(cleaned)
