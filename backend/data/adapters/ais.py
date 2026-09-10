"""AIS-derived fleet density and draft distributions.

Reads a static AIS position dump from disk, the kind published on Kaggle from
the MarineCadastre archive. This is not a live feed and is not pretending to be
one: it runs on a committed or downloaded file, and its output describes the
period that file covers.

Two things are derived:

*Fleet density per corridor.* Distinct hulls seen inside each trade-lane
bounding box. A corridor that is thick with tonnage is a corridor where the
charterer has options; one that is thin is where rates get away from you.

*Draft distribution per vessel class.* What ships of each size actually sail at,
as opposed to what the class table says they could. This is the number that
tells you whether a Panamax fixture into a fourteen-metre berth is routine or
optimistic, and it feeds the berth resolver's assumptions.

Expected columns, matching the MarineCadastre schema most Kaggle AIS sets use::

    MMSI, BaseDateTime, LAT, LON, SOG, VesselType, Length, Width, Draft

Anything else in the file is ignored. Missing columns are reported, not fatal.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from app import config
from data.adapters.base import SourceAdapter

log = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"MMSI", "BaseDateTime", "LAT", "LON"}
USEFUL_COLUMNS = ["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "VesselType", "Length", "Width", "Draft"]

#: AIS ship-type codes 70-79 are the cargo group, which is where bulk carriers sit.
CARGO_TYPE_RANGE = (70, 79)

#: Length overall in metres to vessel class. Drawn from the class definitions in
#: app/reference.py, with gaps assigned to the nearer class.
CLASS_BY_LENGTH: list[tuple[float, float, str]] = [
    (120.0, 190.0, "Handysize"),
    (190.0, 210.0, "Supramax"),
    (210.0, 240.0, "Panamax"),
    (240.0, 1000.0, "Capesize"),
]


def classify_length(length_m: float) -> str | None:
    for low, high, name in CLASS_BY_LENGTH:
        if low <= length_m < high:
            return name
    return None


def load_corridors(path: Path) -> list[dict]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh).get("corridors", [])
    except (OSError, ValueError) as exc:
        log.warning("no corridor definitions at %s: %s", path, exc)
        return []


class AISAdapter(SourceAdapter):
    name = "ais"
    source_label = "Static AIS position dump (MarineCadastre / Kaggle), offline"
    is_proxy = False

    def __init__(self, path: Path | None = None, corridors: Path | None = None) -> None:
        super().__init__()
        self.path = path or config.AIS_FILE
        self.corridors_path = corridors or config.CORRIDORS_FILE

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.path.exists():
            problems.append(
                f"AIS file {self.path} not present; corridor density and draft "
                "distributions will be unavailable. See backend/README.md for where to get it."
            )
        if not self.corridors_path.exists():
            problems.append(f"corridor definitions {self.corridors_path} missing")
        return problems

    def _read(self) -> pd.DataFrame:
        """Read the dump, taking only the columns we use.

        AIS dumps run to millions of rows, so this reads in chunks and keeps
        just the cargo vessels rather than pulling the whole file into memory.
        """
        header = pd.read_csv(self.path, nrows=0)
        available = [c for c in USEFUL_COLUMNS if c in header.columns]
        missing = REQUIRED_COLUMNS - set(available)
        if missing:
            raise ValueError(f"AIS file missing required columns {sorted(missing)}")

        keep: list[pd.DataFrame] = []
        for chunk in pd.read_csv(self.path, usecols=available, chunksize=250_000):
            if "VesselType" in chunk.columns:
                types = pd.to_numeric(chunk["VesselType"], errors="coerce")
                chunk = chunk[types.between(*CARGO_TYPE_RANGE)]
            if not chunk.empty:
                keep.append(chunk)
        if not keep:
            raise ValueError("no cargo-vessel rows in the AIS file")
        return pd.concat(keep, ignore_index=True)

    def fetch(self) -> pd.DataFrame:
        if not self.path.exists():
            raise FileNotFoundError(f"AIS file {self.path} not found")

        raw = self._read()
        raw["BaseDateTime"] = pd.to_datetime(raw["BaseDateTime"], errors="coerce")
        raw = raw.dropna(subset=["BaseDateTime", "LAT", "LON"])
        if raw.empty:
            raise ValueError("AIS file produced no usable positions")

        # The dump is a static window. Stamp everything at its last observation
        # so the age of the data is visible rather than implied to be today.
        stamp = raw["BaseDateTime"].max().normalize()
        span_days = max(1, (raw["BaseDateTime"].max() - raw["BaseDateTime"].min()).days)
        self.notes.append(
            f"static AIS window {raw['BaseDateTime'].min().date()} to {stamp.date()} "
            f"({span_days} days, {len(raw):,} cargo positions)"
        )

        rows: list[dict] = []

        # ── Fleet density per corridor ───────────────────────────────────────
        corridors = load_corridors(self.corridors_path)
        for corridor in corridors:
            box = corridor.get("bbox") or {}
            try:
                inside = raw[
                    raw["LAT"].between(float(box["lat_min"]), float(box["lat_max"]))
                    & raw["LON"].between(float(box["lon_min"]), float(box["lon_max"]))
                ]
            except (KeyError, TypeError, ValueError):
                log.warning("corridor %s has an unusable bbox", corridor.get("id"))
                continue

            cid = corridor.get("id", "unknown")
            rows.append({"timestamp": stamp, "metric": f"ais.corridor.{cid}.vessel_count",
                         "value": float(inside["MMSI"].nunique()), "source": "ais:static"})
            if "SOG" in inside.columns and not inside.empty:
                sog = pd.to_numeric(inside["SOG"], errors="coerce")
                sog = sog[sog.between(1, 25)]  # drop moored and bad fixes
                if not sog.empty:
                    rows.append({"timestamp": stamp, "metric": f"ais.corridor.{cid}.avg_sog_kts",
                                 "value": float(sog.mean()), "source": "ais:static"})

        if corridors and all(r["value"] == 0 for r in rows if r["metric"].endswith("vessel_count")):
            self.notes.append(
                "every corridor came back empty; most public AIS dumps are US coastal "
                "and will not cover Indian Ocean lanes"
            )

        # ── Draft distribution per vessel class ──────────────────────────────
        if {"Length", "Draft"}.issubset(raw.columns):
            geo = raw.copy()
            geo["Length"] = pd.to_numeric(geo["Length"], errors="coerce")
            geo["Draft"] = pd.to_numeric(geo["Draft"], errors="coerce")
            geo = geo.dropna(subset=["Length", "Draft"])
            geo = geo[(geo["Draft"] > 3) & (geo["Draft"] < 26)]
            # One row per hull, so a ship that reported a thousand times does
            # not dominate the distribution.
            geo = geo.groupby("MMSI").agg(Length=("Length", "median"), Draft=("Draft", "median"))
            geo["vessel_class"] = geo["Length"].map(classify_length)
            geo = geo.dropna(subset=["vessel_class"])

            for vessel_class, group in geo.groupby("vessel_class"):
                drafts = group["Draft"].to_numpy(dtype=float)
                for suffix, value in (
                    ("count", float(len(drafts))),
                    ("mean", float(np.mean(drafts))),
                    ("p50", float(np.percentile(drafts, 50))),
                    ("p90", float(np.percentile(drafts, 90))),
                ):
                    rows.append({
                        "timestamp": stamp,
                        "metric": f"ais.draft.{str(vessel_class).lower()}.{suffix}",
                        "value": value,
                        "source": "ais:static",
                    })
        else:
            self.notes.append("AIS file has no Length or Draft column; draft distribution skipped")

        if not rows:
            raise ValueError("AIS file yielded no derived metrics")
        return pd.DataFrame(rows)
