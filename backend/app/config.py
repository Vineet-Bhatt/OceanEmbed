from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """All settings can be overridden with OCEAN_<NAME> env vars or a .env file."""

    model_config = SettingsConfigDict(env_prefix="OCEAN_", env_file=BACKEND_DIR / ".env", extra="ignore")

    artifacts_dir: Path = BACKEND_DIR / "artifacts"   # model weights, norm stats, climatology
    cache_dir: Path = BACKEND_DIR / "cache"           # downloaded + regridded daily fields
    device: str = "auto"                      # auto | cpu | cuda
    batch_size: int = 1024
    copernicusmarine_service_username: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "COPERNICUSMARINE_SERVICE_USERNAME",
            "OCEAN_COPERNICUSMARINE_SERVICE_USERNAME",
        ),
    )
    copernicusmarine_service_password: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "COPERNICUSMARINE_SERVICE_PASSWORD",
            "OCEAN_COPERNICUSMARINE_SERVICE_PASSWORD",
        ),
    )
    earthdata_username: str | None = Field(
        default=None,
        validation_alias=AliasChoices("EARTHDATA_USERNAME", "OCEAN_EARTHDATA_USERNAME"),
    )
    earthdata_password: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("EARTHDATA_PASSWORD", "OCEAN_EARTHDATA_PASSWORD"),
    )

    # --- refresh / caching -------------------------------------------------
    auto_refresh: bool = True
    refresh_interval_min: int = 120
    max_lookback_days: int = 14        # how far back from today to hunt for the newest usable day
    retention_days: int = 30          # prune cached days older than this (relative to newest day)
    mem_days: int = 40                # days kept in RAM (ready-to-use tensors)
    allow_ondemand_download: bool = True
    max_stale_days_sss: int = 14      # SSS NRT is only produced weekly -> allow persistence fill
    max_stale_days_default: int = 3   # gap tolerance for every other variable

    max_batch_points: int = 5000
    admin_api_key: str | None = None  # if set, /admin/* needs header X-API-Key

    # --- data sources (tried in order; first hit wins) -------------------------
    sst_datasets: list[str] = [
        "METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2",
        "METOFFICE-GLO-SST-L4-REP-OBS-SST",
    ]
    sss_datasets: list[str] = [
        "cmems_obs-mob_glo_phy-sss_nrt_multi_P1D",
        "cmems_obs-mob_glo_phy-sss_my_multi_P1D",
    ]
    ssh_datasets: list[str] = [
        "cmems_obs-sl_glo_phy-ssh_nrt_allsat-l4-duacs-0.125deg_P1D",
        "cmems_obs-sl_glo_phy-ssh_my_allsat-l4-duacs-0.125deg_P1D",
    ]
    oscar_short_names: list[str] = [
        "OSCAR_L4_OC_FINAL_V2.0",
        "OSCAR_L4_OC_INTERIM_V2.0",
        "OSCAR_L4_OC_NRT_V2.0",
    ]
    ccmp_erddap_url: str = "https://oceanwatch.pifsc.noaa.gov/erddap/griddap/ccmp-daily-v2-1-NRT.nc"
    ccmp_final_template: str = (
        "https://data.remss.com/ccmp/v03.1/Y{yyyy}/M{mm}/CCMP_Wind_Analysis_{yyyymmdd}_V03.1_L4.nc"
    )
    ccmp_final_after_days: int = 75   # try the final (V3.1) product first for days older than this
    ccmp_min_steps: int = 2           # min 6-hourly steps (of 4) to accept a daily mean
