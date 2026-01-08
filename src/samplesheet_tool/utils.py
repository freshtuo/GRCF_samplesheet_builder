# utils.py
# helpers
# 

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Literal

import math
import pandas as pd

def _is_missing(x) -> bool:
    """missing value?"""
    if x is None:
        return True
    # pandas NA / numpy.nan
    if pd.isna(x):
        return True
    # plain float nan
    if isinstance(x, float) and math.isnan(x):
        return True
    return False

def normalize_seq(s: str | None) -> Optional[str]:
    if _is_missing(s):
        return None
    if s is None:
        return None
    v = str(s).strip().upper().replace(" ", "")
    # extra safety for strings like "nan"
    if v in {"", "NAN", "NA", "NONE"}:
        return None
    return v

def hamming(a: str | None, b: str | None) -> Optional[int]:
    a = normalize_seq(a)
    b = normalize_seq(b)
    if a is None or b is None:
        return None
    if len(a) != len(b):
        return None
    return sum(ch1 != ch2 for ch1, ch2 in zip(a, b))

@dataclass(frozen=True)
class Problem:
    level: Literal["ERROR", "WARN", "INFO"]
    code: str
    message: str
    lane: Optional[int] = None
    sample_id: Optional[str] = None

