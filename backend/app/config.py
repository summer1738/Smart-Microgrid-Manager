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
    auto_train_enabled: bool = False
    auto_train_interval_minutes: int = 360  # every 6 hours
    auto_train_history_hours: int = 168  # export window for training
    auto_train_min_samples: int = 200  # minimum CSV rows before training
    # MQTT (when use_hardware_simulation=False)
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883

    class Config:
        env_prefix = "MICROGRID_"
        env_file = ".env"


settings = Settings()
