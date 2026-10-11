Run `export_artifacts_cell.py` as a notebook cell -> `artifacts/{norm_stats.json, monthly_clim.npy, best_thermocline_model.pt}`
`pip install -r requirements.txt`, copy `.env.example` to `.env` and fill in
`uvicorn app.main:create_app --factory --host`

## Endpoints
`GET /predict?lat=15&lon=68[&date=YYYY-MM-DD]` one profile (422 if the point is land or outside the grid)
`POST /predict/batch` `{"points":[{"lat":..,"lon":..}], "date": null}` up to 5000 points, one model batch
`GET /status` newest cached day
`GET /health`
`POST /admin/refresh` | force a refresh

Each response lists, per input variable, whether the value for the target day was `fetched` or
`filled` (persisted from an earlier day) and its `data_date`.

## How the data side works
* A background task (every 2 h, plus once at start-up) finds the **newest day whose real inputs are
  published**, downloads that day and its 6 predecessors, regrids to the notebook grid
  (0.25 deg, 5-30N 45-105E, linear interp; CCMP 6-hourly -> daily mean) and stores each day as
  `cache/daily/YYYY-MM-DD.npz`. The last 40 days also sit in RAM as ready-made normalised tensors, so a
  prediction does no I/O. After a restart it serves from the disk cache immediately.
* "Today" does not exist in any of these products. Typical lags: OSCAR NRT ~2 days, CCMP NRT <48 h,
  OSTIA/SLA about a day, SSS NRT is produced weekly. So the service keeps the newest *available* day warm
  and moves forward on its own. SSS (only) may be persistence-filled (<=14 days); every other variable
  must be real for a day to count as the newest one (<=3-day gap tolerance inside the window).
* A request for an older `date` downloads its window on demand (disable with `OCEAN_ALLOW_ONDEMAND_DOWNLOAD=false`).
* Use one uvicorn worker: each worker would otherwise download and hold its own copy.

## Sources
SST `METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2` (OSTIA, Kelvin - auto-matched to your training units) |
SSS `cmems_obs-mob_glo_phy-sss_nrt_multi_P1D` | SSH `cmems_obs-sl_glo_phy-ssh_nrt_allsat-l4-duacs-0.125deg_P1D` |
OSCAR `OSCAR_L4_OC_{FINAL,INTERIM,NRT}_V2.0` (best quality first) |
CCMP NRT V2.1 from NOAA CoastWatch ERDDAP (`pifscCcmpDailyV21NRT`), RSS V3.1 final for days older than 75 days.
Check ids with `copernicusmarine describe --contains OSTIA` if a download logs "dataset not found".
Change them if they don't work out
## Tests
`pytest tests` (no torch/network needed): patch extraction is checked element-for-element against the
notebook's `get_batch` indexing; cache/fill/refresh logic and the API run against fakes.
