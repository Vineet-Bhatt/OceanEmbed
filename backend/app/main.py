"""FastAPI service for the ThermoclineAwareOceanModel (final_fast.ipynb).

Run:  uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000     (use ONE worker)
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
from contextlib import asynccontextmanager

import numpy as np
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import Settings
from .grid import DEPTHS, FEATURE_VARS, LAT, LON, extract_patches, load_norm_stats, snap
from .sources import Sources
from .store import DataStore, DataUnavailable

log = logging.getLogger("ocean.api")


# ----------------------------------------------------------------------------- schemas
class Point(BaseModel):
    lat: float = Field(ge=-90, le=90, examples=[15.0])
    lon: float = Field(ge=-180, le=360, examples=[68.0])


class BatchRequest(BaseModel):
    points: list[Point] = Field(min_length=1)
    date: dt.date | None = Field(default=None, description="Target day; default = newest available")


class ProfileLevel(BaseModel):
    depth_m: float
    temperature_c: float
    climatology_c: float
    anomaly_c: float


class PointResult(BaseModel):
    requested: Point
    grid_lat: float | None = None
    grid_lon: float | None = None
    valid: bool
    reason: str | None = None
    profile: list[ProfileLevel] | None = None


class VarFreshness(BaseModel):
    status: str            # "fetched" (real data for that day) | "filled" (persisted from an earlier day)
    data_date: dt.date
    age_days: int


class PredictResponse(BaseModel):
    target_date: dt.date
    window: list[dt.date]
    input_freshness: dict[str, VarFreshness]
    results: list[PointResult]


# ----------------------------------------------------------------------------- app
async def _refresh_loop(store: DataStore, minutes: int):
    while True:
        try:
            await asyncio.to_thread(store.refresh)
        except Exception:
            log.exception("refresh loop error")
        await asyncio.sleep(minutes * 60)


def create_app(settings: Settings | None = None, predictor=None, sources=None) -> FastAPI:
    s = settings or Settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    stats = load_norm_stats(s.artifacts_dir / "norm_stats.json")
    if predictor is None:
        from .model import Predictor            # imported lazily so torch is only needed in production
        predictor = Predictor(s.artifacts_dir, s.device, s.batch_size)
    store = DataStore(s, sources or Sources(s, stats), stats)
    store.init_from_disk()                      # instant readiness after a restart

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(_refresh_loop(store, s.refresh_interval_min)) if s.auto_refresh else None
        yield
        if task:
            task.cancel()

    app = FastAPI(title="Subsurface Ocean Temperature API", version="1.0", lifespan=lifespan)
    app.state.store, app.state.predictor, app.state.settings = store, predictor, s
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------ core
    def run_predict(points: list[Point], date: dt.date | None) -> PredictResponse:
        today = dt.datetime.now(dt.timezone.utc).date()
        if date is None:
            if store.latest_target is None:
                raise HTTPException(503, "Warming up: the first data download is still running.",
                                    headers={"Retry-After": "60"})
            target = store.latest_target
        elif date > today:
            raise HTTPException(400, "date is in the future")
        else:
            target = date
        try:
            window, recs = store.get_window(target, s.allow_ondemand_download)
        except DataUnavailable as e:
            raise HTTPException(503, str(e), headers={"Retry-After": "300"})

        n = len(points)
        la, lo, inside = snap([p.lat for p in points], [p.lon for p in points])
        cand = np.where(inside)[0]
        clim = np.full((n, len(DEPTHS)), np.nan, np.float32)
        center = np.full((n, len(FEATURE_VARS)), np.nan, np.float32)
        if cand.size:
            clim[cand] = predictor.climatology(target.month, la[cand], lo[cand])
            center[cand] = recs[-1].data[:, la[cand], lo[cand]].T
        ok = inside & np.isfinite(clim).all(1) & np.isfinite(center).all(1)

        temp = np.full((n, len(DEPTHS)), np.nan, np.float32)
        idx = np.where(ok)[0]
        if idx.size:
            x = extract_patches(window, la[idx], lo[idx])
            temp[idx], _ = predictor.predict(x, clim[idx])

        results = []
        for i, p in enumerate(points):
            if ok[i]:
                prof = [ProfileLevel(depth_m=d, temperature_c=round(float(temp[i, k]), 3),
                                     climatology_c=round(float(clim[i, k]), 3),
                                     anomaly_c=round(float(temp[i, k] - clim[i, k]), 3))
                        for k, d in enumerate(DEPTHS)]
                results.append(PointResult(requested=p, grid_lat=float(LAT[la[i]]), grid_lon=float(LON[lo[i]]),
                                           valid=True, profile=prof))
            else:
                if not inside[i]:
                    why = "outside the model domain (5-30N, 45-105E)"
                elif not np.isfinite(clim[i]).all():
                    why = "outside the model's training mask (land or shallow water)"
                else:
                    why = "input data missing at this grid point (land or no satellite coverage)"
                results.append(PointResult(requested=p, valid=False, reason=why))

        return PredictResponse(
            target_date=target, window=store.window_days(target),
            input_freshness=store.freshness(recs[-1], today), results=results)

    # ------------------------------------------------------------------ routes
    @app.get("/health")
    def health():
        return {"status": "ok", "ready": store.latest_target is not None}

    @app.get("/status")
    def status():
        latest = store.latest_target
        rec = store.get_record(latest) if latest is not None else None
        fresh = store.freshness(rec) if rec is not None else None
        return {
            "ready": latest is not None, "latest_target_date": latest,
            "last_refresh_utc": store.last_refresh, "refreshing": store.refreshing,
            "last_error": store.last_error, "cached_days": store.cached_days(),
            "latest_input_freshness": fresh,
            "device": str(getattr(predictor, "device", "n/a")),
        }

    @app.get("/predict", response_model=PredictResponse)
    def predict(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=360),
                date: dt.date | None = Query(None, description="YYYY-MM-DD; default = newest available day")):
        res = run_predict([Point(lat=lat, lon=lon)], date)
        if not res.results[0].valid:
            raise HTTPException(422, res.results[0].reason)
        return res

    @app.post("/predict/batch", response_model=PredictResponse)
    def predict_batch(req: BatchRequest):
        if len(req.points) > s.max_batch_points:
            raise HTTPException(413, f"max {s.max_batch_points} points per request")
        return run_predict(req.points, req.date)

    @app.post("/admin/refresh", status_code=202)
    def admin_refresh(background: BackgroundTasks, x_api_key: str | None = Header(None)):
        if s.admin_api_key and x_api_key != s.admin_api_key:
            raise HTTPException(401, "bad or missing X-API-Key")
        if store.refreshing:
            return {"status": "already running"}
        background.add_task(store.refresh)
        return {"status": "started"}

    return app
