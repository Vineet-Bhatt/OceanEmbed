"""Downloads one day of each input variable and regrids it to the model grid (0.25 deg,
5-30N / 45-105E) with the same linear interpolation the notebook used.

Every public fetch is best-effort: a source that is down or hasn't published the day yet
simply returns nothing and the store decides what to do (retry later / persistence fill).
"""
from __future__ import annotations

import logging
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import numpy as np
import xarray as xr

from .config import Settings
from .grid import LAT, LON

log = logging.getLogger("ocean.sources")
PAD = 1.0   # degrees of margin fetched around the region so interpolation has neighbours

_EARTHDATA_READY = False
_EARTHDATA_ERR: str | None = None     # set once if earthaccess is missing / login impossible
_HOST_DOWN_UNTIL: dict[str, float] = {}   # host -> monotonic time until which we skip it
HOST_COOLDOWN_S = 300.0


# ----------------------------------------------------------------------------- helpers
def _why(e: BaseException, limit: int = 160) -> str:
    """Short, safe description of an exception (never raises, even for empty messages)."""
    lines = str(e).splitlines()
    msg = lines[0][:limit] if lines else ""
    return f"{type(e).__name__}: {msg}" if msg else type(e).__name__


def _retry(fn, attempts: int = 2, delay: float = 3.0):
    """Call fn(); on any exception wait and try again, re-raising the last one."""
    for i in range(attempts):
        try:
            return fn()
        except Exception:
            if i == attempts - 1:
                raise
            time.sleep(delay)


def _std_names(ds: xr.Dataset) -> xr.Dataset:
    ren = {}
    for short, full in (("lat", "latitude"), ("lon", "longitude")):
        if short in ds.coords and full in ds.dims and full not in ds.coords:
            ds = ds.assign_coords({full: ds[short].data}).drop_vars(short)
        elif (short in ds.variables or short in ds.dims) and full not in ds.variables and full not in ds.dims:
            ren[short] = full
    return ds.rename(ren) if ren else ds


def regrid(da: xr.DataArray) -> np.ndarray:
    """(…, latitude, longitude) DataArray -> float32 [101, 241] on the model grid."""
    da = da.squeeze(drop=True).transpose("latitude", "longitude")
    da = da.sortby("latitude").sortby("longitude")
    da = da.sel(latitude=slice(LAT[0] - PAD, LAT[-1] + PAD),
                longitude=slice(LON[0] - PAD, LON[-1] + PAD))
    out = da.interp(latitude=LAT, longitude=LON, method="linear")
    return out.values.astype(np.float32)


def oscar_from_dataset(ds: xr.Dataset) -> dict[str, np.ndarray]:
    ds = _std_names(ds)
    if "time" in ds.dims:
        ds = ds.isel(time=0)
    return {"u": regrid(ds["u"]), "v": regrid(ds["v"])}


def ccmp_from_dataset(ds: xr.Dataset, min_steps: int) -> dict[str, np.ndarray] | None:
    """6-hourly CCMP -> daily mean (the notebook's resample('1D').mean())."""
    ds = _std_names(ds)
    if "time" in ds.dims:
        if ds.sizes["time"] < min_steps:
            return None
        ds = ds.mean("time", skipna=True)
    return {"uwnd": regrid(ds["uwnd"]), "vwnd": regrid(ds["vwnd"])}


def _download(url: str, dest: Path, timeout: float = 180.0,
              connect_timeout: float = 10.0, attempts: int = 2) -> bool:
    """Stream url to dest. Returns False on 404/other non-200 (no retry) or if the host is
    unreachable. Transport errors and HTTP 5xx are retried with backoff; a host that cannot
    be reached is skipped for HOST_COOLDOWN_S so a backfill doesn't stall on every day."""
    import httpx
    host = urlparse(url).netloc
    if _HOST_DOWN_UNTIL.get(host, 0.0) > time.monotonic():
        log.info("skipping %s (marked unreachable, cooling down)", host)
        return False

    tmo = httpx.Timeout(timeout, connect=connect_timeout)
    for i in range(1, attempts + 1):
        try:
            with httpx.stream("GET", url, timeout=tmo, follow_redirects=True) as r:
                if r.status_code >= 500:
                    log.warning("GET %s -> HTTP %s (attempt %d/%d)",
                                url.split("?")[0], r.status_code, i, attempts)
                elif r.status_code != 200:
                    log.info("GET %s -> HTTP %s", url.split("?")[0], r.status_code)
                    return False            # e.g. 404 = not published yet; retrying won't help
                else:
                    with open(dest, "wb") as fh:
                        for chunk in r.iter_bytes():
                            fh.write(chunk)
                    _HOST_DOWN_UNTIL.pop(host, None)
                    return True
        except httpx.TransportError as e:   # DNS failure, connect timeout, reset, read timeout
            log.warning("GET %s attempt %d/%d failed: %s", host, i, attempts, _why(e))
            if isinstance(e, (httpx.ConnectError, httpx.ConnectTimeout)):
                _HOST_DOWN_UNTIL[host] = time.monotonic() + HOST_COOLDOWN_S
                return False                # unreachable: retrying immediately won't help
        if i < attempts:
            time.sleep(2 ** i)
    return False


# ----------------------------------------------------------------------------- sources
class Sources:
    def __init__(self, settings: Settings, norm_stats: dict[str, tuple[float, float]]):
        self.s = settings
        self.stats = norm_stats

    # --- Copernicus Marine: SST (OSTIA), SSS (multi-obs), SSH (DUACS SLA) ---------------
    def _cmems(self, dataset_ids: list[str], var: str, day: date) -> np.ndarray | None:
        import copernicusmarine   # credentials: `copernicusmarine login` or COPERNICUSMARINE_SERVICE_* env vars
        for ds_id in dataset_ids:
            try:
                ds = copernicusmarine.open_dataset(
                    dataset_id=ds_id, variables=[var],
                    username=self.s.copernicusmarine_service_username,
                    password=(
                        self.s.copernicusmarine_service_password.get_secret_value()
                        if self.s.copernicusmarine_service_password else None
                    ),
                    # daily products are stamped 00:00; ending at 23:59:59 overshoots the newest
                    # timestamp and raises CoordinatesOutOfDatasetBounds, so ask for 00:00 only
                    start_datetime=f"{day.isoformat()}T00:00:00",
                    end_datetime=f"{day.isoformat()}T00:00:00",
                    minimum_latitude=float(LAT[0] - PAD), maximum_latitude=float(LAT[-1] + PAD),
                    minimum_longitude=float(LON[0] - PAD), maximum_longitude=float(LON[-1] + PAD),
                )
                if ds.sizes.get("time", 0) == 0:
                    continue
                ds = ds.isel(time=0)
                if "depth" in ds.dims:       # SSS ships with a singleton depth axis (notebook squeezes it)
                    ds = ds.isel(depth=0)
                return regrid(ds[var].load())
            except Exception as e:           # not published yet / dataset id moved / auth / network
                log.info("%s %s %s: %s", ds_id, var, day, _why(e))
        return None

    # --- OSCAR (NASA PO.DAAC via earthaccess) -------------------------------------------
    def _earthdata_login(self) -> bool:
        """Log in once per process. On a permanent problem (module missing, no credentials)
        log a single actionable warning and disable OSCAR until restart."""
        global _EARTHDATA_READY, _EARTHDATA_ERR
        if _EARTHDATA_READY:
            return True
        if _EARTHDATA_ERR:
            return False
        try:
            import earthaccess
        except ImportError:
            _EARTHDATA_ERR = "earthaccess not installed"
            log.warning("OSCAR disabled: earthaccess is not installed in this environment. "
                        "Run: %s -m pip install earthaccess", __import__("sys").executable)
            return False
        if self.s.earthdata_username and not os.environ.get("EARTHDATA_USERNAME"):
            os.environ["EARTHDATA_USERNAME"] = self.s.earthdata_username
        if self.s.earthdata_password and not os.environ.get("EARTHDATA_PASSWORD"):
            os.environ["EARTHDATA_PASSWORD"] = self.s.earthdata_password.get_secret_value()
        last = None
        for strategy in ("environment", "netrc"):   # env vars first, then ~/.netrc (_netrc on Windows)
            try:
                auth = earthaccess.login(strategy=strategy, persist=False)
                if getattr(auth, "authenticated", True):
                    _EARTHDATA_READY = True
                    return True
            except Exception as e:
                last = e
        _EARTHDATA_ERR = "earthdata login failed"
        log.warning("OSCAR disabled: Earthdata login failed (%s). Set EARTHDATA_USERNAME and "
                    "EARTHDATA_PASSWORD (or EARTHDATA_TOKEN), or add a .netrc entry for "
                    "urs.earthdata.nasa.gov.", _why(last) if last else "no credentials found")
        return False

    def _oscar(self, day: date) -> dict[str, np.ndarray] | None:
        if not self._earthdata_login():
            return None
        import earthaccess
        stamp = day.strftime("%Y%m%d")
        for short in self.s.oscar_short_names:          # best quality first: final -> interim -> nrt
            try:
                res = _retry(lambda: earthaccess.search_data(
                    short_name=short,
                    temporal=(day.isoformat(), (day + timedelta(days=1)).isoformat())))
                links = [l for g in res for l in g.data_links() if stamp in l and l.endswith(".nc")]
                if not links:
                    continue                      # not published yet for this product
                with tempfile.TemporaryDirectory() as tmp:
                    files = _retry(lambda: earthaccess.download(links[:1], tmp))
                    if not files:
                        continue
                    with xr.open_dataset(str(files[0]), decode_times=False) as ds:
                        return oscar_from_dataset(ds.load())
            except Exception as e:
                log.warning("OSCAR %s %s failed: %s", short, day, _why(e))
        return None

    # --- CCMP winds ---------------------------------------------------------------------
    def _ccmp_nrt(self, day: date) -> xr.Dataset | None:
        t0, t1 = f"{day.isoformat()}T00:00:00Z", f"{day.isoformat()}T18:00:00Z"
        box = f"[({LAT[0] - PAD}):1:({LAT[-1] + PAD})][({LON[0] - PAD}):1:({LON[-1] + PAD})]"
        query = ",".join(f"{v}[({t0}):1:({t1})]{box}" for v in ("uwnd", "vwnd"))
        url = f"{self.s.ccmp_erddap_url}?{quote(query, safe='(),:')}"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ccmp_nrt.nc"
            if not _download(url, path):
                return None
            with xr.open_dataset(path) as ds:
                return ds.load()

    def _ccmp_final(self, day: date) -> xr.Dataset | None:
        url = self.s.ccmp_final_template.format(
            yyyy=day.year, mm=f"{day.month:02d}", yyyymmdd=day.strftime("%Y%m%d"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ccmp_final.nc"
            if not _download(url, path, timeout=300):
                return None
            with xr.open_dataset(path) as ds:
                return ds.load()

    def _ccmp_podaac(self, day: date) -> xr.Dataset | None:
        """Fallback: the same RSS CCMP V3.1 daily file (4 x 6-hourly steps), fetched from NASA
        PO.DAAC via earthaccess. Reachable when the ERDDAP / RSS hosts are not, but PO.DAAC
        only publishes it ~2-3 months after the fact, so it helps older days, not the newest."""
        if not self._earthdata_login():
            return None
        import earthaccess
        short = getattr(self.s, "ccmp_podaac_short_name", "CCMP_WINDS_10M6HR_L4_V3.1")
        stamp = day.strftime("%Y%m%d")
        res = _retry(lambda: earthaccess.search_data(
            short_name=short,
            temporal=(day.isoformat(), (day + timedelta(days=1)).isoformat())))
        links = [l for g in res for l in g.data_links() if stamp in l and l.endswith(".nc")]
        if not links:
            return None                           # not published yet
        with tempfile.TemporaryDirectory() as tmp:
            files = _retry(lambda: earthaccess.download(links[:1], tmp))
            if not files:
                return None
            with xr.open_dataset(str(files[0])) as ds:
                return ds.load()

    def _ccmp(self, day: date) -> dict[str, np.ndarray] | None:
        age = (datetime.now(timezone.utc).date() - day).days
        podaac_min_age = getattr(self.s, "ccmp_podaac_min_age_days", 30)
        order = []
        if age > self.s.ccmp_final_after_days:
            order.append("final")                 # RSS host, final quality
        if age >= podaac_min_age:
            order.append("podaac")                # same final product via NASA, if RSS is down
        order.append("nrt")                       # ERDDAP near-real-time
        fetchers = {"final": self._ccmp_final, "podaac": self._ccmp_podaac, "nrt": self._ccmp_nrt}
        for kind in order:
            try:
                ds = fetchers[kind](day)
                if ds is None:
                    continue
                out = ccmp_from_dataset(ds, self.s.ccmp_min_steps)
                if out:
                    return out
                log.warning("CCMP %s %s: fewer than %d time steps available",
                            kind, day, self.s.ccmp_min_steps)
            except Exception as e:
                log.warning("CCMP %s %s failed: %s", kind, day, _why(e))
        return None

    # --- unit alignment -----------------------------------------------------------------
    def _align_sst_units(self, arr: np.ndarray) -> np.ndarray:
        """OSTIA is in Kelvin. Match whatever unit the training SST used (inferred from norm stats)."""
        train_mean = self.stats["analysed_sst"][0]
        m = float(np.nanmean(arr)) if np.isfinite(arr).any() else np.nan
        if m > 200 and train_mean < 100:
            return arr - 273.15
        if m < 100 and train_mean > 200:
            return arr + 273.15
        return arr

    # --- public -------------------------------------------------------------------------
    def fetch(self, day: date, wanted: set[str]) -> dict[str, np.ndarray]:
        """Fetch the wanted variables for one day. Returns only what was actually obtained."""
        jobs = {}
        with ThreadPoolExecutor(max_workers=4) as ex:
            if "analysed_sst" in wanted:
                jobs["analysed_sst"] = ex.submit(self._cmems, self.s.sst_datasets, "analysed_sst", day)
            if "sos" in wanted:
                jobs["sos"] = ex.submit(self._cmems, self.s.sss_datasets, "sos", day)
            if "sla" in wanted:
                jobs["sla"] = ex.submit(self._cmems, self.s.ssh_datasets, "sla", day)
            if wanted & {"u", "v"}:
                jobs["oscar"] = ex.submit(self._oscar, day)
            if wanted & {"uwnd", "vwnd"}:
                jobs["ccmp"] = ex.submit(self._ccmp, day)

        out: dict[str, np.ndarray] = {}
        for key, fut in jobs.items():
            try:
                res = fut.result()
            except Exception as e:
                log.warning("fetch %s %s failed: %s", key, day, _why(e))
                continue
            if res is None:
                continue
            if isinstance(res, np.ndarray):
                res = {key: res}
            for var, arr in res.items():
                if var in wanted and np.isfinite(arr).any():
                    out[var] = self._align_sst_units(arr) if var == "analysed_sst" else arr
        return out