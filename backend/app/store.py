"""Daily cache of regridded inputs.

Disk:   cache/daily/YYYY-MM-DD.npz  (raw units, [7,101,241] + per-variable status/source date)
RAM:    last `mem_days` days as ready-to-use normalised float16 tensors -> predictions never touch
        the network or disk on the hot path.

A background refresh keeps the newest available day (and its 6 predecessors) downloaded.
"""
from __future__ import annotations

import logging
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import numpy as np

from .config import Settings
from .grid import FEATURE_VARS, N_LAT, N_LON, N_VARS, WINDOW, normalise_pad

log = logging.getLogger("ocean.store")

MISSING, FETCHED, FILLED = 0, 1, 2
# SSS is only produced weekly, so it may be persistence-filled; everything else must be real
# for a day to count as "ready" (usable as the newest prediction date).
CRITICAL = [i for i, v in enumerate(FEATURE_VARS) if v != "sos"]


class DataUnavailable(RuntimeError):
    pass


@dataclass
class DayRecord:
    day: date
    data: np.ndarray      # [V,H,W] float32 raw units, NaN where missing
    status: np.ndarray    # [V] int8  0 missing / 1 fetched for this day / 2 filled from an earlier day
    src: np.ndarray       # [V] int32 ordinal of the day the values really come from

    @classmethod
    def empty(cls, day: date) -> "DayRecord":
        return cls(day, np.full((N_VARS, N_LAT, N_LON), np.nan, np.float32),
                   np.zeros(N_VARS, np.int8), np.zeros(N_VARS, np.int32))

    @property
    def complete(self) -> bool:
        return bool(np.all(self.status > MISSING))

    @property
    def fresh(self) -> bool:
        return bool(np.all(self.status[CRITICAL] == FETCHED))

    def missing_vars(self) -> list[str]:
        return [v for v, s in zip(FEATURE_VARS, self.status) if s == MISSING]


class DataStore:
    def __init__(self, settings: Settings, sources, norm_stats):
        self.s = settings
        self.sources = sources
        self.stats = norm_stats
        self.dir = settings.cache_dir / "daily"
        self.dir.mkdir(parents=True, exist_ok=True)

        self._io_lock = threading.RLock()        # short critical sections (dict / small file ops)
        self._refresh_lock = threading.Lock()    # long network operations
        self._mem: "OrderedDict[date, tuple[DayRecord, np.ndarray]]" = OrderedDict()

        self.latest_target: date | None = None
        self.last_refresh: datetime | None = None
        self.last_error: str | None = None
        self.refreshing = False

    # ------------------------------------------------------------------ disk
    def _path(self, d: date):
        return self.dir / f"{d.isoformat()}.npz"

    def load_day(self, d: date) -> DayRecord | None:
        p = self._path(d)
        if not p.exists():
            return None
        try:
            with np.load(p) as z:
                return DayRecord(d, z["data"], z["status"], z["src"])
        except Exception as e:                    # corrupt/partial file -> treat as absent
            log.warning("unreadable cache file %s (%s); ignoring", p.name, e)
            return None

    def save_day(self, rec: DayRecord) -> None:
        tmp = self.dir / f".{rec.day.isoformat()}.tmp.npz"
        np.savez_compressed(tmp, data=rec.data, status=rec.status, src=rec.src)
        os.replace(tmp, self._path(rec.day))
        self._mem_put(rec)

    # ------------------------------------------------------------------ RAM
    def _mem_put(self, rec: DayRecord) -> None:
        norm = normalise_pad(rec.data, self.stats)
        with self._io_lock:
            self._mem[rec.day] = (rec, norm)
            self._mem.move_to_end(rec.day)
            while len(self._mem) > self.s.mem_days:
                self._mem.popitem(last=False)

    def _mem_get(self, d: date):
        with self._io_lock:
            hit = self._mem.get(d)
            if hit is not None:
                self._mem.move_to_end(d)
            return hit

    # ------------------------------------------------------------------ building days
    def _max_stale(self, var: str) -> int:
        return self.s.max_stale_days_sss if var == "sos" else self.s.max_stale_days_default

    def _fill(self, d: date, i: int) -> tuple[np.ndarray, int] | None:
        """Persistence fill: latest earlier value of variable i within its stale limit."""
        var, limit = FEATURE_VARS[i], self._max_stale(FEATURE_VARS[i])
        for k in range(1, limit + 1):             # 1) the cache
            prev = self.load_day(d - timedelta(days=k))
            if prev is not None and prev.status[i] != MISSING:
                src = int(prev.src[i])
                if d.toordinal() - src <= limit:
                    return prev.data[i].copy(), src
                return None
        for k in range(1, limit + 1):             # 2) cold start: ask the source directly
            got = self.sources.fetch(d - timedelta(days=k), {var})
            if var in got:
                return got[var], (d - timedelta(days=k)).toordinal()
        return None

    def build_day(self, d: date, allow_fill: bool) -> DayRecord:
        rec = self.load_day(d) or DayRecord.empty(d)
        need = {v for v, s in zip(FEATURE_VARS, rec.status) if s != FETCHED}
        if not need:
            return rec
        for var, arr in self.sources.fetch(d, need).items():
            i = FEATURE_VARS.index(var)
            rec.data[i], rec.status[i], rec.src[i] = arr, FETCHED, d.toordinal()
        if allow_fill:
            for i in range(N_VARS):
                if rec.status[i] == FETCHED:
                    continue
                filled = self._fill(d, i)
                if filled is not None:
                    rec.data[i], rec.src[i], rec.status[i] = filled[0], filled[1], FILLED
        self.save_day(rec)
        return rec

    @staticmethod
    def window_days(target: date) -> list[date]:
        return [target - timedelta(days=WINDOW - 1 - j) for j in range(WINDOW)]

    # ------------------------------------------------------------------ refresh
    def refresh(self) -> bool:
        """Find the newest day whose real inputs exist, and make sure its 7-day window is cached.
        Safe to call repeatedly / concurrently (a second concurrent call returns False)."""
        if not self._refresh_lock.acquire(blocking=False):
            return False
        self.refreshing = True
        try:
            today = datetime.now(timezone.utc).date()
            target = None
            for k in range(self.s.max_lookback_days + 1):
                d = today - timedelta(days=k)
                if self.build_day(d, allow_fill=False).fresh:
                    target = d
                    break
            if target is None:
                self.last_error = (f"no day in the last {self.s.max_lookback_days} days had all "
                                   "critical inputs published yet")
                log.warning(self.last_error)
                return False
            for d in self.window_days(target):          # oldest -> newest so fills can chain
                self.build_day(d, allow_fill=True)
            self.latest_target = target
            self.last_error = None
            self.last_refresh = datetime.now(timezone.utc)
            self._prune()
            log.info("refresh ok: newest usable day %s", target)
            return True
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            log.exception("refresh failed")
            return False
        finally:
            self.refreshing = False
            self._refresh_lock.release()

    def init_from_disk(self) -> None:
        """After a restart, serve immediately from the on-disk cache while a refresh runs."""
        days = sorted((date.fromisoformat(p.stem) for p in self.dir.glob("????-??-??.npz")), reverse=True)
        for d in days:
            rec = self.load_day(d)
            if rec is None or not rec.fresh:
                continue
            recs = [self.load_day(x) for x in self.window_days(d)]
            if all(r is not None and r.complete for r in recs):
                for r in recs:
                    self._mem_put(r)
                self.latest_target = d
                log.info("restored cache: newest usable day %s", d)
                return

    def _prune(self) -> None:
        if self.latest_target is None:
            return
        cutoff = self.latest_target - timedelta(days=self.s.retention_days)
        for p in self.dir.glob("????-??-??.npz"):
            if date.fromisoformat(p.stem) < cutoff:
                p.unlink(missing_ok=True)

    # ------------------------------------------------------------------ hot path
    def get_window(self, target: date, allow_download: bool):
        """-> (window float16 [T,V,Hp,Wp] oldest->newest, [DayRecord x T])"""
        recs, norms = [], []
        for d in self.window_days(target):
            hit = self._mem_get(d)
            if hit is None or not hit[0].complete:
                rec = self.load_day(d)
                if (rec is None or not rec.complete) and allow_download:
                    with self._refresh_lock:                # waits if a refresh is mid-flight
                        rec = self.build_day(d, allow_fill=True)
                if rec is None:
                    raise DataUnavailable(f"inputs for {d} are not cached")
                if not rec.complete:
                    raise DataUnavailable(f"inputs for {d} unavailable (missing: {', '.join(rec.missing_vars())})")
                self._mem_put(rec)
                hit = self._mem_get(d)
            recs.append(hit[0])
            norms.append(hit[1])
        return np.stack(norms), recs

    @staticmethod
    def freshness(rec: DayRecord, today: date | None = None) -> dict[str, dict]:
        today = today or datetime.now(timezone.utc).date()
        out = {}
        for i, v in enumerate(FEATURE_VARS):
            src = date.fromordinal(int(rec.src[i]))
            out[v] = {"status": "fetched" if rec.status[i] == FETCHED else "filled",
                      "data_date": src, "age_days": (today - src).days}
        return out

    def get_record(self, d: date) -> DayRecord | None:
        hit = self._mem_get(d)
        return hit[0] if hit else self.load_day(d)

    def cached_days(self) -> list[str]:
        return sorted(p.stem for p in self.dir.glob("????-??-??.npz"))
