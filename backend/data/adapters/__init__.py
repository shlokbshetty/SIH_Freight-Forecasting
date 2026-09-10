"""Adapter registry.

One place that knows which sources exist. Everything else asks here, so adding
a source is a single edit and removing one cannot leave a dangling reference.
"""

from __future__ import annotations

import logging

from data.adapters.ais import AISAdapter
from data.adapters.baltic import BalticAdapter
from data.adapters.base import FetchOutcome, SourceAdapter
from data.adapters.bunker import BunkerAdapter
from data.adapters.commodity import CommodityAdapter
from data.adapters.congestion import CongestionAdapter
from data.adapters.equity import EquityProxyAdapter
from data.adapters.macro import MacroAdapter
from data.adapters.weather import WeatherAdapter

log = logging.getLogger(__name__)

__all__ = [
    "AISAdapter", "BalticAdapter", "BunkerAdapter", "CommodityAdapter",
    "CongestionAdapter", "EquityProxyAdapter", "MacroAdapter", "WeatherAdapter",
    "FetchOutcome", "SourceAdapter", "build_adapters", "validate_all", "adapter_metadata",
]

ADAPTER_CLASSES: list[type[SourceAdapter]] = [
    BalticAdapter,
    EquityProxyAdapter,
    CommodityAdapter,
    MacroAdapter,
    BunkerAdapter,
    CongestionAdapter,
    WeatherAdapter,
    AISAdapter,
]


def build_adapters() -> list[SourceAdapter]:
    adapters: list[SourceAdapter] = []
    for cls in ADAPTER_CLASSES:
        try:
            adapters.append(cls())
        except Exception as exc:  # noqa: BLE001 - a broken constructor loses one source, not all
            log.warning("could not construct %s: %s", cls.__name__, exc)
    return adapters


def validate_all(adapters: list[SourceAdapter] | None = None) -> dict[str, list[str]]:
    """Startup health check.

    Every adapter reports its own problems. A dead ticker, a missing file or an
    absent credential is logged once here, clearly, rather than turning into
    silent NaNs in a feature frame three layers down.
    """
    report: dict[str, list[str]] = {}
    for adapter in adapters or build_adapters():
        try:
            problems = adapter.validate()
        except Exception as exc:  # noqa: BLE001
            problems = [f"validation raised {type(exc).__name__}: {exc}"]
        report[adapter.name] = problems
        for problem in problems:
            log.warning("source %r: %s", adapter.name, problem)
    return report


def adapter_metadata() -> dict[str, dict]:
    """name -> {source_label, is_proxy}, for /api/data/status."""
    return {
        cls.name: {"source_label": cls.source_label, "is_proxy": cls.is_proxy}
        for cls in ADAPTER_CLASSES
    }
