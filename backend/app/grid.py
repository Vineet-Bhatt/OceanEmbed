"""Grid constants and the numpy-side pre-processing that mirrors the notebook exactly."""
import json
from pathlib import Path

import numpy as np

LAT = np.arange(5, 30.25, 0.25)       # 101 points  (target_lat in the notebook)
LON = np.arange(45, 105.25, 0.25)     # 241 points  (target_lon)
STEP = 0.25
N_LAT, N_LON = LAT.size, LON.size
DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]
FEATURE_VARS = ["analysed_sst", "sos", "sla", "u", "v", "uwnd", "vwnd"]
N_VARS = len(FEATURE_VARS)
WINDOW = 7       # TEMPORAL_WINDOW
PATCH = 5        # PATCH_SIZE
HALF = PATCH // 2


def snap(lat, lon):
    """Nearest grid node. Returns (lat_idx, lon_idx, inside_mask)."""
    la = np.rint((np.asarray(lat, dtype=float) - LAT[0]) / STEP).astype(int)
    lo = np.rint((np.asarray(lon, dtype=float) - LON[0]) / STEP).astype(int)
    inside = (la >= 0) & (la < N_LAT) & (lo >= 0) & (lo < N_LON)
    return la, lo, inside


def load_norm_stats(path: Path) -> dict[str, tuple[float, float]]:
    raw = json.loads(Path(path).read_text())
    missing = [v for v in FEATURE_VARS if v not in raw]
    if missing:
        raise ValueError(f"norm_stats.json is missing variables: {missing}")
    return {v: (float(raw[v][0]), float(raw[v][1])) for v in FEATURE_VARS}


def normalise_pad(raw: np.ndarray, stats: dict[str, tuple[float, float]]) -> np.ndarray:
    """raw [V,H,W] float32 -> [V,H+2h,W+2h] float16.

    Same recipe as OceanTemporalDataset: z-score with (std+1e-8), NaN/inf -> 0,
    zero-pad by HALF AFTER normalisation, store as float16.
    """
    out = np.zeros((N_VARS, N_LAT + 2 * HALF, N_LON + 2 * HALF), dtype=np.float16)
    for k, var in enumerate(FEATURE_VARS):
        mean, std = stats[var]
        arr = np.nan_to_num((raw[k].astype(np.float32) - mean) / (std + 1e-8),
                            nan=0.0, posinf=0.0, neginf=0.0)
        out[k, HALF:HALF + N_LAT, HALF:HALF + N_LON] = arr.astype(np.float16)
    return out


def extract_patches(window: np.ndarray, la: np.ndarray, lo: np.ndarray) -> np.ndarray:
    """window [T,V,Hp,Wp] float16 (oldest->newest), la/lo [B] grid indices
    -> [B,T,V,PATCH,PATCH] float32 (same layout as OceanTemporalDataset.get_batch)."""
    ar = np.arange(PATCH)
    li = la[:, None, None] + ar[None, :, None]        # B,5,1  (padded coords)
    oi = lo[:, None, None] + ar[None, None, :]        # B,1,5
    x = window[:, :, li, oi]                          # T,V,B,5,5
    return np.ascontiguousarray(x.transpose(2, 0, 1, 3, 4)).astype(np.float32)
