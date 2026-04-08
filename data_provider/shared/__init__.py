# -*- coding: utf-8 -*-
"""
Shared infrastructure for data provider managers.

Provides rate limiting and persistent caching used across
FundamentalManager, NewsManager, and MacroManager.
"""

from .rate_limiter import RateLimit, SharedRateLimiter
from .cache import ProviderCache

__all__ = ["RateLimit", "SharedRateLimiter", "ProviderCache"]
