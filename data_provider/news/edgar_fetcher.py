# -*- coding: utf-8 -*-
"""
SEC EDGAR news/filings fetcher.

Tertiary provider, priority 2. Free, no API key required.
Uses the EDGAR full-text search API to find recent 8-K filings.

Requires User-Agent header with email (SEC policy).
Read from SEC_EDGAR_USER_AGENT env var; falls back to a default.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import requests

from .base import BaseNewsFetcher
from .types import NewsEventType, UnifiedNewsItem

logger = logging.getLogger(__name__)

_EFTS_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
_DEFAULT_USER_AGENT = "DSA-StockAnalysis/1.0 (contact@example.com)"


class EDGARNewsFetcher(BaseNewsFetcher):
    """SEC EDGAR filings fetcher (priority 2).

    Free, no API key required. Fetches recent 8-K filings via
    the EDGAR full-text search API.
    """

    name = "edgar"
    priority = 2

    def __init__(self) -> None:
        self._user_agent = (
            os.environ.get("SEC_EDGAR_USER_AGENT", "").strip()
            or _DEFAULT_USER_AGENT
        )

    def is_available(self) -> bool:
        # EDGAR is always available (no API key needed)
        return True

    @property
    def _headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self._user_agent,
            "Accept": "application/json",
        }

    def get_news(self, stock_code: str, days: int = 7) -> List[UnifiedNewsItem]:
        symbol = stock_code.strip().upper()
        now = datetime.now(timezone.utc)
        start_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")

        items: List[UnifiedNewsItem] = []

        try:
            # Use EDGAR full-text search API
            params = {
                "q": f'"{symbol}"',
                "dateRange": "custom",
                "startdt": start_date,
                "enddt": end_date,
                "forms": "8-K",
            }
            resp = requests.get(
                _EFTS_SEARCH_URL,
                headers=self._headers,
                params=params,
                timeout=15,
            )

            if resp.status_code != 200:
                logger.warning(
                    "[edgar] HTTP %s from EFTS search for %s", resp.status_code, symbol
                )
                return []

            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])

            for hit in hits:
                try:
                    source = hit.get("_source", {})
                    file_date = source.get("file_date", "")
                    form_type = source.get("form_type", "8-K")
                    entity_name = source.get("entity_name", "")
                    file_num = source.get("file_num", "")

                    # Parse date
                    try:
                        published = datetime.strptime(file_date, "%Y-%m-%d").replace(
                            tzinfo=timezone.utc
                        )
                    except (ValueError, TypeError):
                        published = now

                    # Build EDGAR filing URL
                    accession = source.get("accession_no", "").replace("-", "")
                    if accession:
                        filing_url = (
                            f"https://www.sec.gov/Archives/edgar/data/"
                            f"{accession[:10].lstrip('0')}/{accession}"
                        )
                    else:
                        filing_url = "https://www.sec.gov/cgi-bin/browse-edgar"

                    title = f"{form_type} Filing: {entity_name}" if entity_name else f"{form_type} Filing for {symbol}"

                    items.append(
                        UnifiedNewsItem(
                            title=title,
                            url=filing_url,
                            published_at=published,
                            source_name="edgar",
                            tickers=[symbol],
                            event_type=NewsEventType.SEC_FILING,
                            summary=f"SEC {form_type} filing by {entity_name} (file #{file_num})"
                            if entity_name
                            else None,
                        )
                    )
                except Exception as e:
                    logger.debug("[edgar] Error parsing filing hit: %s", e)
                    continue

        except requests.exceptions.RequestException as e:
            logger.warning("[edgar] Request error for %s: %s", symbol, e)
        except Exception as e:
            logger.warning("[edgar] Unexpected error for %s: %s", symbol, e)

        return items
