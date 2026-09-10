"""Weather and monsoon conditions at the discharge ports.

Open-Meteo, free and unauthenticated, and it takes every coordinate in one call
so seven ports cost one request.

This feeds the map's weather layer and the risk screen. The projection model
does not read it: the monsoon term there is derived from the calendar, because a
fourteen-day forecast cannot tell a model anything about a rate six months out.
What this is for is the near-term operational picture, where a week of heavy
weather on the Paradip approach is the difference between berthing and waiting.
"""

from __future__ import annotations

import logging

import pandas as pd

from app.reference import DISCHARGE_PORTS, berth_port_name
from data.adapters.base import SourceAdapter, http_get

log = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

#: Daily rainfall above this is enough to stop cargo work on an open berth.
WORK_STOPPING_PRECIP_MM = 12.0


class WeatherAdapter(SourceAdapter):
    name = "weather"
    source_label = "Open-Meteo daily forecast for the seven discharge ports"
    is_proxy = False

    def __init__(self, ports=None) -> None:
        super().__init__()
        self.ports = list(ports or DISCHARGE_PORTS)

    def fetch(self) -> pd.DataFrame:
        payload = http_get(
            OPEN_METEO_URL,
            {
                "latitude": ",".join(f"{p.lat:.4f}" for p in self.ports),
                "longitude": ",".join(f"{p.lng:.4f}" for p in self.ports),
                "daily": "precipitation_sum,wind_speed_10m_max",
                "past_days": 7,
                "forecast_days": 14,
                "timezone": "UTC",
            },
        )

        # One location comes back as an object, several as a list.
        blocks = payload if isinstance(payload, list) else [payload]
        if len(blocks) != len(self.ports):
            raise ValueError(f"expected {len(self.ports)} locations, got {len(blocks)}")

        frames: list[pd.DataFrame] = []
        for port, block in zip(self.ports, blocks):
            daily = block.get("daily") or {}
            times = daily.get("time") or []
            if not times:
                continue
            key = berth_port_name(port.id)
            for field, suffix in (
                ("precipitation_sum", "precip_mm"),
                ("wind_speed_10m_max", "wind_kmh"),
            ):
                values = daily.get(field) or []
                frames.append(
                    pd.DataFrame(
                        {
                            "timestamp": pd.to_datetime(times[: len(values)]),
                            "metric": f"weather.{key}.{suffix}",
                            "value": values,
                            "source": "open-meteo",
                        }
                    ).dropna(subset=["value"])
                )

        if not frames:
            raise ValueError("open-meteo returned no daily series")

        combined = pd.concat(frames, ignore_index=True)

        # A derived flag the map and risk screens can colour on directly, rather
        # than each of them re-deciding what counts as bad weather.
        rain = combined[combined["metric"].str.endswith(".precip_mm")].copy()
        if not rain.empty:
            rain["metric"] = rain["metric"].str.replace(".precip_mm", ".work_stopped", regex=False)
            rain["value"] = (rain["value"] >= WORK_STOPPING_PRECIP_MM).astype(float)
            rain["source"] = f"derived:precip>={WORK_STOPPING_PRECIP_MM:.0f}mm"
            combined = pd.concat([combined, rain], ignore_index=True)

        return combined
