"""Torch-free tests: patch extraction vs the notebook's indexing, caching/fill logic, API wiring.
(The network downloaders and the real model forward pass are NOT exercised here.)"""
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr
from fastapi.testclient import TestClient

from app.config import Settings
from app.grid import (DEPTHS, FEATURE_VARS, HALF, LAT, LON, N_LAT, N_LON, PATCH, WINDOW,
                      extract_patches, normalise_pad, snap)
from app.main import create_app
from app import sources as sources_module
from app.sources import ccmp_from_dataset, oscar_from_dataset, regrid
from app.store import FETCHED, FILLED, DataStore

TODAY = datetime.now(timezone.utc).date()
STATS = {v: (10.0 * (i + 1), 2.0 + i) for i, v in enumerate(FEATURE_VARS)}


# ------------------------------------------------------------------ fakes
class FakeSources:
    """Deterministic data; availability rules mimic real latencies."""
    def __init__(self):
        self.calls = []
        self.sss_available_until = TODAY - timedelta(days=4)   # weekly SSS lags
        self.oscar_lag = 2                                      # OSCAR NRT ~2 days

    def fetch(self, day, wanted):
        self.calls.append((day, frozenset(wanted)))
        out = {}
        for v in wanted:
            i = FEATURE_VARS.index(v)
            if v == "sos" and day > self.sss_available_until:
                continue
            if v in ("u", "v") and (TODAY - day).days < self.oscar_lag:
                continue
            if (TODAY - day).days < 1 and v != "uwnd":   # nothing but a bit of wind for "today"
                continue
            out[v] = np.full((N_LAT, N_LON), day.toordinal() % 100 + 0.1 * i, np.float32)
        return out


class FakePredictor:
    device = "fake"
    def climatology(self, month, la, lo):
        c = np.tile(np.linspace(28, 5, len(DEPTHS), dtype=np.float32), (len(la), 1))
        c[lo < 4] = np.nan                                      # "land" in the west
        return c
    def predict(self, x, clim):
        assert x.shape[1:] == (WINDOW, len(FEATURE_VARS), PATCH, PATCH) and x.dtype == np.float32
        return clim + 0.5, np.full_like(clim, 0.5)


@pytest.fixture
def env(tmp_path):
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "norm_stats.json").write_text(json.dumps({k: list(v) for k, v in STATS.items()}))
    s = Settings(artifacts_dir=tmp_path / "artifacts", cache_dir=tmp_path / "cache",
                 auto_refresh=False, admin_api_key="secret")
    src = FakeSources()
    app = create_app(s, predictor=FakePredictor(), sources=src)
    return app, src, TestClient(app)


# ------------------------------------------------------------------ grid / notebook equivalence
def test_snap_and_grid_shape():
    assert (N_LAT, N_LON) == (101, 241)
    la, lo, ok = snap([5, 30, 30.1, 30.2, 4.9], [45, 105, 105.1, 105.2, 44.9])
    assert la.tolist()[:3] == [0, 100, 100] and lo.tolist()[:3] == [0, 240, 240]
    assert ok.tolist() == [True, True, True, False, True]


def test_normalise_pad_matches_notebook_recipe():
    rng = np.random.default_rng(0)
    raw = rng.normal(20, 3, (7, N_LAT, N_LON)).astype(np.float32)
    raw[1, 10, 10] = np.nan
    out = normalise_pad(raw, STATS)
    assert out.dtype == np.float16 and out.shape == (7, N_LAT + 4, N_LON + 4)
    assert out[1, 10 + HALF, 10 + HALF] == 0                  # NaN -> 0 after normalisation
    assert np.all(out[:, :HALF] == 0) and np.all(out[:, :, -HALF:] == 0)   # zero border
    k = 3
    exp = ((raw[k] - STATS[FEATURE_VARS[k]][0]) / (STATS[FEATURE_VARS[k]][1] + 1e-8)).astype(np.float16)
    assert np.array_equal(out[k, HALF:-HALF, HALF:-HALF], exp)


def test_extract_patches_equals_notebook_get_batch():
    rng = np.random.default_rng(1)
    data = rng.normal(size=(12, 7, N_LAT + 4, N_LON + 4)).astype(np.float16)   # [T,V,Hp,Wp]
    rows = np.array([[9, 0, 0], [9, 100, 240], [9, 50, 120], [9, 3, 237]])
    # notebook's OceanTemporalDataset.get_batch, transcribed to numpy
    t, la, lo = rows[:, 0], rows[:, 1], rows[:, 2]
    ar_t, ar_p, ar_v = np.arange(-WINDOW + 1, 1), np.arange(PATCH), np.arange(7)
    ti, li, oi = t[:, None] + ar_t, la[:, None] + ar_p, lo[:, None] + ar_p
    ref = data[ti[:, :, None, None, None], ar_v[None, None, :, None, None],
               li[:, None, None, :, None], oi[:, None, None, None, :]].astype(np.float32)
    mine = extract_patches(data[t[0] - WINDOW + 1: t[0] + 1], la, lo)
    assert ref.shape == mine.shape == (4, 7, 7, 5, 5)
    assert np.array_equal(ref, mine)


# ------------------------------------------------------------------ source parsing / regrid
def test_regrid_and_parsers():
    lat = np.arange(3, 33, 0.125); lon = np.arange(40, 110, 0.125)
    f = lambda la, lo: (la * 2 + lo * 0.5).astype(np.float32)
    field = f(lat[:, None], lon[None, :])
    da = xr.DataArray(field[::-1], dims=("latitude", "longitude"),                # descending lat on purpose
                      coords={"latitude": lat[::-1], "longitude": lon})
    out = regrid(da)
    assert out.shape == (N_LAT, N_LON)
    assert np.allclose(out, f(LAT[:, None], LON[None, :]), atol=1e-3)

    # OSCAR style: dims (time, lon, lat) with lat/lon names
    ds = xr.Dataset({"u": (("time", "lon", "lat"), np.ones((1, lon.size, lat.size), np.float32)),
                     "v": (("time", "lon", "lat"), 2 * np.ones((1, lon.size, lat.size), np.float32))},
                    coords={"time": [0.0], "lon": lon, "lat": lat})
    o = oscar_from_dataset(ds)
    assert np.allclose(o["u"], 1) and np.allclose(o["v"], 2)

    # OSCAR files can put lat/lon coordinate variables on already-named dimensions.
    oscar = xr.Dataset(
        {"u": (("time", "longitude", "latitude"), np.ones((1, lon.size, lat.size), np.float32)),
         "v": (("time", "longitude", "latitude"), 2 * np.ones((1, lon.size, lat.size), np.float32))},
        coords={"time": [0.0], "lat": ("latitude", lat), "lon": ("longitude", lon)},
    )
    normalized_oscar = oscar_from_dataset(oscar)
    assert np.allclose(normalized_oscar["u"], 1) and np.allclose(normalized_oscar["v"], 2)

    # CCMP: 4 six-hourly steps -> daily mean
    la2, lo2 = np.arange(3, 33, 0.25), np.arange(40, 110, 0.25)
    steps = np.arange(4, dtype=np.float32)[:, None, None] * np.ones((4, la2.size, lo2.size), np.float32)
    ds = xr.Dataset({"uwnd": (("time", "latitude", "longitude"), steps),
                     "vwnd": (("time", "latitude", "longitude"), -steps)},
                    coords={"time": np.arange(4), "latitude": la2, "longitude": lo2})
    c = ccmp_from_dataset(ds, min_steps=2)
    assert np.allclose(c["uwnd"], 1.5) and np.allclose(c["vwnd"], -1.5)
    assert ccmp_from_dataset(ds.isel(time=slice(0, 1)), min_steps=2) is None


def test_provider_credentials_are_passed_to_clients(monkeypatch, tmp_path):
    settings = Settings(
        artifacts_dir=tmp_path / "artifacts",
        cache_dir=tmp_path / "cache",
        copernicusmarine_service_username="cm-user",
        copernicusmarine_service_password="cm-password",
        earthdata_username="ed-user",
        earthdata_password="ed-password",
    )
    opened = {}

    def open_dataset(**kwargs):
        opened.update(kwargs)
        return xr.Dataset({"analysed_sst": (("time",), [1.0])}, coords={"time": [0]})

    monkeypatch.setitem(sys.modules, "copernicusmarine",
                        SimpleNamespace(open_dataset=open_dataset))
    monkeypatch.setattr(sources_module, "regrid", lambda data: np.ones((N_LAT, N_LON), np.float32))
    source = sources_module.Sources(settings, STATS)
    assert source._cmems(["dataset"], "analysed_sst", TODAY) is not None
    assert opened["username"] == "cm-user"
    assert opened["password"] == "cm-password"

    monkeypatch.delenv("EARTHDATA_USERNAME", raising=False)
    monkeypatch.delenv("EARTHDATA_PASSWORD", raising=False)
    monkeypatch.setattr(sources_module, "_EARTHDATA_READY", False)
    monkeypatch.setattr(sources_module, "_EARTHDATA_ERR", None)
    login_calls = []

    def login(**kwargs):
        login_calls.append(kwargs)
        return SimpleNamespace(authenticated=True)

    monkeypatch.setitem(sys.modules, "earthaccess", SimpleNamespace(login=login))
    assert source._earthdata_login()
    assert login_calls == [{"strategy": "environment", "persist": False}]
    assert login_calls and source.s.earthdata_username == "ed-user"
    assert os.environ["EARTHDATA_PASSWORD"] == "ed-password"


# ------------------------------------------------------------------ store behaviour
def test_refresh_picks_newest_real_day_fills_sss_and_reuses_cache(env):
    app, src, _ = env
    store: DataStore = app.state.store
    assert store.refresh() is True
    assert store.latest_target == TODAY - timedelta(days=2)       # OSCAR lag decides
    rec = store.get_record(store.latest_target)
    sos = FEATURE_VARS.index("sos")
    assert rec.status[sos] == FILLED and date.fromordinal(int(rec.src[sos])) == TODAY - timedelta(days=4)
    assert all(rec.status[i] == FETCHED for i in range(7) if i != sos)
    assert rec.complete and rec.fresh
    assert len(store.cached_days()) >= WINDOW

    # SSS finally arrives -> next refresh upgrades filled -> fetched
    src.sss_available_until = TODAY
    store.refresh()
    assert store.get_record(store.latest_target).status[sos] == FETCHED

    # fully-fetched days are never downloaded again
    src.calls.clear()
    store.refresh()
    for day, wanted in src.calls:
        rec = store.get_record(day)
        assert not (rec is not None and rec.status[0] == FETCHED and "analysed_sst" in wanted and day <= store.latest_target)


def test_restart_serves_from_disk_cache(env, tmp_path):
    app, _, _ = env
    app.state.store.refresh()
    s = app.state.settings
    app2 = create_app(s, predictor=FakePredictor(), sources=FakeSources())
    assert app2.state.store.latest_target == app.state.store.latest_target


def test_prune(env):
    app, _, _ = env
    st: DataStore = app.state.store
    st.refresh()
    old = st.dir / f"{(st.latest_target - timedelta(days=90)).isoformat()}.npz"
    old.write_bytes(b"x")
    st._prune()
    assert not old.exists()


# ------------------------------------------------------------------ API
def test_api_flow(env):
    app, _, client = env
    assert client.get("/health").json() == {"status": "ok", "ready": False}
    assert client.get("/predict", params=dict(lat=15, lon=68)).status_code == 503   # warming up

    app.state.store.refresh()
    assert client.get("/health").json()["ready"] is True
    st = client.get("/status").json()
    assert st["ready"] and st["latest_input_freshness"]["sos"]["status"] == "filled"

    r = client.get("/predict", params=dict(lat=15.06, lon=68.1))
    assert r.status_code == 200
    j = r.json()
    res = j["results"][0]
    assert res["grid_lat"] == 15.0 and res["grid_lon"] == 68.0 and res["valid"]
    assert len(res["profile"]) == 15 and res["profile"][0]["depth_m"] == 0
    assert abs(res["profile"][3]["anomaly_c"] - 0.5) < 1e-3
    assert j["target_date"] == (TODAY - timedelta(days=2)).isoformat() and len(j["window"]) == 7

    bad = client.get("/predict", params=dict(lat=15, lon=45.2))                      # "land"
    assert bad.status_code == 422 and "training mask" in bad.json()["detail"]
    assert client.get("/predict", params=dict(lat=60, lon=68)).status_code == 422    # outside domain

    b = client.post("/predict/batch", json={"points": [{"lat": 10, "lon": 70}, {"lat": 15, "lon": 45.2},
                                                       {"lat": 50, "lon": 70}, {"lat": 20, "lon": 90}]})
    assert b.status_code == 200
    assert [x["valid"] for x in b.json()["results"]] == [True, False, False, True]
    assert b.json()["results"][1]["profile"] is None

    assert client.get("/predict", params=dict(lat=15, lon=68, date=str(TODAY + timedelta(days=3)))).status_code == 400
    older = TODAY - timedelta(days=12)                                                # on-demand window
    assert client.get("/predict", params=dict(lat=15, lon=68, date=str(older))).status_code == 200


def test_ondemand_disabled_and_admin_key(env):
    app, _, client = env
    app.state.store.refresh()
    app.state.settings.allow_ondemand_download = False
    old = TODAY - timedelta(days=20)
    assert client.get("/predict", params=dict(lat=15, lon=68, date=str(old))).status_code == 503
    assert client.post("/admin/refresh").status_code == 401
    assert client.post("/admin/refresh", headers={"X-API-Key": "secret"}).status_code == 202
