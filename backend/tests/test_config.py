import os
from datetime import date

from pydantic import SecretStr

from app.config import BACKEND_DIR, Settings
from app import sources as sources_module
from app.sources import Sources


def test_backend_env_file_and_default_paths_are_absolute():
    assert Settings.model_config["env_file"] == BACKEND_DIR / ".env"
    settings = Settings(_env_file=None)
    assert settings.artifacts_dir == BACKEND_DIR / "artifacts"
    assert settings.cache_dir == BACKEND_DIR / "cache"


def test_settings_load_provider_credentials_from_env_file_outside_backend(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "OCEAN_DEVICE=cpu",
                "COPERNICUSMARINE_SERVICE_USERNAME=cm-user",
                "COPERNICUSMARINE_SERVICE_PASSWORD=cm-password",
                "EARTHDATA_USERNAME=earth-user",
                "EARTHDATA_PASSWORD=earth-password",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    settings = Settings(_env_file=env_file)

    assert settings.device == "cpu"
    assert settings.copernicusmarine_service_username == "cm-user"
    assert settings.copernicusmarine_service_password == SecretStr("cm-password")
    assert settings.earthdata_username == "earth-user"
    assert settings.earthdata_password == SecretStr("earth-password")


def test_settings_accept_ocean_prefixed_provider_credentials(monkeypatch):
    monkeypatch.setenv("OCEAN_COPERNICUSMARINE_SERVICE_USERNAME", "cm-user")
    monkeypatch.setenv("OCEAN_COPERNICUSMARINE_SERVICE_PASSWORD", "cm-password")
    monkeypatch.setenv("OCEAN_EARTHDATA_USERNAME", "earth-user")
    monkeypatch.setenv("OCEAN_EARTHDATA_PASSWORD", "earth-password")

    settings = Settings(_env_file=None)

    assert settings.copernicusmarine_service_username == "cm-user"
    assert settings.copernicusmarine_service_password == SecretStr("cm-password")
    assert settings.earthdata_username == "earth-user"
    assert settings.earthdata_password == SecretStr("earth-password")


def test_copernicus_credentials_are_passed_to_client(monkeypatch):
    settings = Settings(
        _env_file=None,
        copernicusmarine_service_username="cm-user",
        copernicusmarine_service_password=SecretStr("cm-password"),
    )
    source = Sources(settings, {})
    calls = []

    def fake_open_dataset(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("offline")

    monkeypatch.setattr("copernicusmarine.open_dataset", fake_open_dataset)

    assert source._cmems(["dataset"], "variable", date(2026, 1, 1)) is None
    assert calls[0]["username"] == "cm-user"
    assert calls[0]["password"] == "cm-password"


def test_earthdata_credentials_are_available_to_environment_login(monkeypatch):
    monkeypatch.delenv("EARTHDATA_USERNAME", raising=False)
    monkeypatch.delenv("EARTHDATA_PASSWORD", raising=False)
    monkeypatch.setattr(sources_module, "_EARTHDATA_READY", False)
    monkeypatch.setattr(sources_module, "_EARTHDATA_ERR", None)
    settings = Settings(
        _env_file=None,
        earthdata_username="earth-user",
        earthdata_password=SecretStr("earth-password"),
    )
    calls = []
    source = Sources(settings, {})

    class Auth:
        authenticated = True

    monkeypatch.setattr(sources_module.earthaccess, "login", lambda **kwargs: calls.append(kwargs) or Auth())

    assert source._earthdata_login() is True
    assert calls == [{"strategy": "environment"}]
    assert os.environ["EARTHDATA_USERNAME"] == "earth-user"
    assert os.environ["EARTHDATA_PASSWORD"] == "earth-password"
