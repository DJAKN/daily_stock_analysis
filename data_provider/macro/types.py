# -*- coding: utf-8 -*-
"""
Macro economic data types for US stock market analysis.

Defines MacroIndicator (single economic indicator reading),
EconEvent (upcoming economic calendar event), and
UnifiedMacroSnapshot (aggregated macro view with regime label).
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class MacroIndicator:
    """A single macro economic indicator reading.

    Example: Federal Funds Rate = 5.33%, down 0.17 from previous.
    """

    name: str  # "fed_funds_rate"
    display_name: str  # "Federal Funds Rate"
    value: float  # 5.33
    previous_value: Optional[float]  # 5.50
    change: Optional[float]  # -0.17
    unit: str  # "%"
    as_of_date: str  # "2026-03-01"
    source: str  # "fred"


@dataclass
class EconEvent:
    """An upcoming economic calendar event.

    Example: FOMC Meeting on 2026-04-15, high impact.
    """

    event: str  # "FOMC Meeting"
    date: str  # "2026-04-15"
    impact: str  # "high" | "medium" | "low"
    estimate: Optional[float] = None
    previous: Optional[float] = None


@dataclass
class UnifiedMacroSnapshot:
    """Aggregated macro economic snapshot with regime classification.

    Combines indicator readings, upcoming calendar events, and a
    market regime label for downstream LLM analysis.
    """

    timestamp: datetime
    indicators: Dict[str, MacroIndicator] = field(default_factory=dict)
    upcoming_events: List[EconEvent] = field(default_factory=list)
    market_regime: str = "neutral"  # "risk_on" | "risk_off" | "neutral"

    def to_dict(self) -> dict:
        """Serialize to plain dict for JSON / LLM consumption.

        Indicators are serialized as a dict of dicts keyed by name.
        Events are serialized as a list of dicts.
        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "indicators": {
                key: asdict(ind) for key, ind in self.indicators.items()
            },
            "upcoming_events": [asdict(ev) for ev in self.upcoming_events],
            "market_regime": self.market_regime,
        }
