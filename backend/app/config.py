"""Application configuration. Use env vars or .env for overrides."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Backend settings."""

    use_hardware_simulation: bool = True
    database_url: str = "sqlite+aiosqlite:///./microgrid.db"
    simulator_interval_seconds: int = 60
    controller_loop_enabled: bool = True
    controller_tick_on_status_request: bool = False
    # Optional: automatic LSTM retraining loop (runs inside backend process).
    # Requires CPU-only torch installed and enough DB history.
    # Default ON for new installations; user can override via /system/settings in the UI.
    auto_train_enabled: bool = True
    auto_train_interval_minutes: int = 360  # every 6 hours
    auto_train_history_hours: int = 168  # export window for training
    auto_train_min_samples: int = 200  # minimum CSV rows before training
    # MQTT (when use_hardware_simulation=False)
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_topic_prefix: str = "microgrid"
    mqtt_client_id: str = "smart-microgrid-backend"
    # Weather → PV (Open-Meteo, no API key). Used for /forecast and IEBA when LSTM not used.
    weather_forecast_enabled: bool = True
    weather_latitude: float = -17.8
    weather_longitude: float = 31.05
    weather_pv_capacity_kw: float = 1.0
    # Multiply (shortwave_W/m² / 1000) * capacity; accounts for inverter + mismatch (~0.85 typical).
    weather_panel_derate: float = 0.85

    class Config:
        env_prefix = "MICROGRID_"
        env_file = ".env"


settings = Settings()
