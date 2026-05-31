"""Application configuration. Use env vars or .env for overrides."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Backend settings."""

    use_hardware_simulation: bool = False
    database_url: str = "mysql+aiomysql://root:Virus1738%25@localhost:3306/smart_microgrid"
    simulator_interval_seconds: int = 1
    controller_loop_enabled: bool = True
    controller_tick_on_status_request: bool = False
    # Optional: automatic LSTM retraining loop (runs inside backend process).
    # Requires CPU-only torch installed and enough DB history.
    # Default ON for new installations; user can override via /system/settings in the UI.
    auto_train_enabled: bool = True
    auto_train_interval_minutes: int = 360  # every 6 hours
    auto_train_history_hours: int = 168  # export window for training
    auto_train_min_samples: int = 200  # minimum CSV rows before training
    auto_ieba_enabled: bool = False
    auto_ieba_interval_minutes: int = 60
    # MQTT (when use_hardware_simulation=False)
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_topic_prefix: str = "microgrid"
    mqtt_client_id: str = "smart-microgrid-backend"
    # Optional USB serial fallback bridge (ESP32 [USB] JSON -> MQTT topics).
    esp32_usb_fallback_enabled: bool = False
    esp32_usb_port: str = "/dev/ttyUSB0"
    esp32_usb_baudrate: int = 115200
    # Weather → PV (Open-Meteo, no API key). Used for /forecast and IEBA when LSTM not used.
    weather_forecast_enabled: bool = True
    weather_latitude: float = -17.8
    weather_longitude: float = 31.05
    weather_pv_capacity_kw: float = 1.0
    # Multiply (shortwave_W/m² / 1000) * capacity; accounts for inverter + mismatch (~0.85 typical).
    weather_panel_derate: float = 0.85
    # Authentication
    auth_session_cookie_name: str = "smart_microgrid_session"
    auth_session_ttl_hours: int = 24
    auth_password_iterations: int = 390000
    auth_cookie_secure: bool = False
    # Logging
    log_level: str = "INFO"  # DEBUG/INFO/WARNING/ERROR
    log_access: bool = True  # log request method/path/status/duration
    log_color: bool = True  # colorize logs when supported (TTY)

    class Config:
        env_prefix = "MICROGRID_"
        env_file = ".env"
        extra = "ignore"


settings = Settings()
