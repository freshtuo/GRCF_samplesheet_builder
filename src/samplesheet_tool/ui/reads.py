from __future__ import annotations

READS_EPSILON = 1e-9
READS_DISPLAY_DIGITS = 3


def coerce_reads_m(value) -> float:
    """Convert a reads-in-millions value to float."""
    return float(value)


def round_reads_m(value, digits: int = READS_DISPLAY_DIGITS) -> float:
    """Round read counts for stable display without changing stored precision too much."""
    rounded = round(coerce_reads_m(value), digits)
    return 0.0 if abs(rounded) < READS_EPSILON else rounded


def display_reads_m(value, digits: int = READS_DISPLAY_DIGITS):
    """Return a numeric display value, preserving ints where possible for table sorting."""
    rounded = round_reads_m(value, digits=digits)
    if float(rounded).is_integer():
        return int(rounded)
    return rounded


def format_reads_m(value, digits: int = READS_DISPLAY_DIGITS) -> str:
    """Format read counts without trailing zeros."""
    rounded = round_reads_m(value, digits=digits)
    text = f"{rounded:.{digits}f}".rstrip("0").rstrip(".")
    return text or "0"


def format_fraction(value, digits: int = READS_DISPLAY_DIGITS) -> str:
    """Format a ratio as a conventional 0.xxx string."""
    return f"{coerce_reads_m(value):.{digits}f}"


def is_zero_reads(value, eps: float = READS_EPSILON) -> bool:
    """Treat tiny floating point noise as zero."""
    return abs(coerce_reads_m(value)) <= eps
