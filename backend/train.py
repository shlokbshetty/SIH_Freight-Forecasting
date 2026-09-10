#!/usr/bin/env python3
"""Offline training.

Fits one SARIMAX per vessel class, backtests it, pickles the result into
``models/`` and writes ``models/metrics.json`` for the accuracy panel in the UI.

Nothing here ever runs inside a request handler. The API loads the pickles at
startup and only filters new observations through them.

    python train.py                      # every class, from the cached data
    python train.py --classes capesize   # one class
    python train.py --refresh            # pull live data first, then train
    python train.py --no-backtest        # skip scoring, much faster

Exit code is non-zero only if every class failed, so a single bad series does
not break a scripted retrain.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import config  # noqa: E402
from data import cache, ingest  # noqa: E402
from models import project  # noqa: E402

log = logging.getLogger("train")


def train_one(conn, vessel_class: str, *, backtest: bool, folds: int) -> tuple[project.ProjectionBundle, dict]:
    frame = project.build_feature_frame(conn, vessel_class)
    log.info(
        "%s: %s rows, %s to %s",
        vessel_class, len(frame), frame.index[0].date(), frame.index[-1].date(),
    )

    bundle = project.fit(frame, vessel_class)
    log.info(
        "%s: fitted order=%s AIC=%.1f on %s regressors (own driver %s excluded) %s",
        vessel_class, bundle.order, bundle.aic, len(bundle.features),
        project.OWN_DRIVER.get(vessel_class, "none"),
        "converged" if bundle.converged else "DID NOT CONVERGE",
    )
    if frame.attrs.get("missing_features"):
        log.warning("%s: regressors neutralised: %s", vessel_class, frame.attrs["missing_features"])

    scores: dict = {}
    if backtest:
        try:
            scores = project.rolling_origin_backtest(frame, folds=folds, vessel_class=vessel_class)
            for horizon, s in sorted(scores.items(), key=lambda kv: int(kv[0])):
                if s["mape"] is not None:
                    log.info(
                        "%s: %sd MAPE %.2f%%  RMSE %.3f  (%s folds)",
                        vessel_class, horizon, s["mape"], s["rmse"], s["folds"],
                    )
        except Exception as exc:  # noqa: BLE001 - a failed backtest is not a failed model
            log.warning("%s: backtest failed (%s); shipping the model without scores", vessel_class, exc)

    bundle.metrics = scores
    return bundle, scores


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--classes", nargs="*", default=project.VESSEL_CLASSES)
    ap.add_argument("--model-dir", type=Path, default=config.MODEL_DIR)
    ap.add_argument("--refresh", action="store_true", help="run ingestion before training")
    ap.add_argument("--no-backtest", action="store_true")
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    conn = cache.connect(config.CACHE_DB)
    seeded = ingest.bootstrap(conn)
    if seeded:
        log.info("seeded %s observations from the snapshot", seeded)

    if args.refresh:
        log.info("refreshing sources before training")
        for outcome in ingest.refresh_all(conn):
            log.info("  %-10s rows=%-6s stale=%s", outcome.adapter, outcome.rows, outcome.is_stale)

    per_class: dict[str, dict] = {}
    trained = 0

    for vessel_class in args.classes:
        vessel_class = vessel_class.lower()
        try:
            bundle, scores = train_one(
                conn, vessel_class, backtest=not args.no_backtest, folds=args.folds
            )
        except Exception as exc:  # noqa: BLE001 - keep going through the other classes
            log.error("%s: training failed: %s", vessel_class, exc)
            per_class[vessel_class] = {"error": str(exc)}
            continue

        path = project.model_path(args.model_dir, vessel_class)
        bundle.save(path)
        trained += 1
        try:
            shown = path.relative_to(BACKEND_ROOT)
        except ValueError:  # --model-dir pointed outside the backend tree
            shown = path
        log.info("%s: wrote %s", vessel_class, shown)

        per_class[vessel_class] = {
            "horizons": scores,
            "order": list(bundle.order),
            "features": bundle.features,
            "aic": round(bundle.aic, 3),
            "train_rows": bundle.train_rows,
            "train_end": bundle.train_end,
            "trained_at": bundle.trained_at,
            "converged": bundle.converged,
            "model_file": path.name,
        }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "horizons_days": list(project.HORIZONS),
        "backtest": "rolling-origin" if not args.no_backtest else "skipped",
        "classes": per_class,
    }
    project.write_metrics(config.METRICS_FILE, payload)
    log.info("wrote %s", config.METRICS_FILE)

    if trained == 0:
        log.error("no models trained")
        return 1
    log.info("trained %s of %s classes", trained, len(args.classes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
