# -*- coding: utf-8 -*-
"""
Macro economic data provider package.

Provides macro indicator types, economic calendar events,
and fetchers for FRED (indicators) and Finnhub (calendar).
"""

from .types import MacroIndicator, EconEvent, UnifiedMacroSnapshot
from .base import BaseMacroIndicatorFetcher, BaseMacroCalendarFetcher

__all__ = [
    "MacroIndicator",
    "EconEvent",
    "UnifiedMacroSnapshot",
    "BaseMacroIndicatorFetcher",
    "BaseMacroCalendarFetcher",
]
