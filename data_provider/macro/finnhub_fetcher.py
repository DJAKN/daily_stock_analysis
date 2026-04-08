# -*- coding: utf-8 -*-
"""
Finnhub economic calendar fetcher.

Provides upcoming economic events via Finnhub's calendar/economic endpoint.
Uses FINNHUB_API_KEY env var. Free tier: 60 req/min.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import List, Optional

from .base import BaseMacroCalendarFetcher
from .types import EconEvent

logger = logging.getLogger(__name__)

_BASE_URL = "https://finnhub.io/api/v1"

# Finnhub impact mapping: numeric or string -> normalized label
_IMPACT_MAP = {
    1: "low",
    2: "medium",
    3: "high",
    "low": "low",
    "medium": "medium",
    "high": "high",
}


class FinnhubCalendarFetcher(BaseMacroCalendarFetcher):
    """Finnhub economic calendar fetcher."""

    name = "finnhub_calendar"

    def __init__(self) -> None:
        self._api_key = os.environ.get("FINNHUB_API_KEY", "").strip() or None

    def is_available(self) -> bool:
        return self._api_key is not None

    def get_economic_calendar(self, days_ahead: int = 14) -> List[EconEvent]:
        """Fetch upcoming economic calendar events from Finnhub.

        Args:
            days_ahead: Number of days into the future to query.

        Returns list of EconEvent, empty list on failure.
        """
        if not self.is_available():
            logger.debug("[finnhub_calendar] API key not configured, skipping")
            return []

        try:
            today = datetime.now().strftime("%Y-%m-%d")
            end_date = (datetime.now() + timedelta(days=days_ahead)).strftime(
                "%Y-%m-%d"
            )

            url = f"{_BASE_URL}/calendar/economic"
            params = {
                "from": today,
                "to": end_date,
                "token": self._api_key,
            }

            data = self._get_json(url, params=params)
            if not data or not isinstance(data, dict):
                return []

            raw_events = data.get("economicCalendar", [])
            if not isinstance(raw_events, list):
                return []

            events: List[EconEvent] = []
            for raw in raw_events:
                event = self._parse_event(raw)
                if event is not None:
                    events.append(event)

            logger.info(
                "[finnhub_calendar] Fetched %d economic events (%s to %s)",
                len(events),
                today,
                end_date,
            )
            return events

        except Exception as e:
            logger.warning("[finnhub_calendar] Failed to fetch calendar: %s", e)
            return []

    def _parse_event(self, raw: dict) -> Optional[EconEvent]:
        """Parse a single Finnhub calendar entry into EconEvent."""
        event_name = raw.get("event", "")
        event_date = raw.get("date", "")

        if not event_name or not event_date:
            return None

        # Normalize impact
        raw_impact = raw.get("impact", "medium")
        impact = _IMPACT_MAP.get(raw_impact, "medium")

        # Parse numeric fields
        estimate = self._safe_float(raw.get("estimate"))
        previous = self._safe_float(raw.get("prev"))

        return EconEvent(
            event=event_name,
            date=event_date,
            impact=impact,
            estimate=estimate,
            previous=previous,
        )

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        """Convert to float, returning None for None/invalid."""
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None
