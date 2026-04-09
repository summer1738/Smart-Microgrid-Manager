"""Shared MQTT topic builders and parsers for backend and Pi emulator."""


def _clean_prefix(prefix: str) -> str:
    return prefix.strip().strip("/")


def sensor_pv_topic(prefix: str) -> str:
    return f"{_clean_prefix(prefix)}/sensors/pv"


def sensor_battery_topic(prefix: str) -> str:
    return f"{_clean_prefix(prefix)}/sensors/battery"


def sensor_environment_topic(prefix: str) -> str:
    """ESP32/gateway: DHT11 + digital light (JSON)."""
    return f"{_clean_prefix(prefix)}/sensors/environment"


def sensor_load_topic(prefix: str, appliance_external_id: str) -> str:
    return f"{_clean_prefix(prefix)}/sensors/load/{appliance_external_id}"


def command_relay_topic(prefix: str, appliance_external_id: str) -> str:
    return f"{_clean_prefix(prefix)}/cmd/relay/{appliance_external_id}"


def ack_relay_topic(prefix: str, appliance_external_id: str) -> str:
    return f"{_clean_prefix(prefix)}/ack/relay/{appliance_external_id}"


def parse_sensor_load_topic(prefix: str, topic: str) -> str | None:
    base = f"{_clean_prefix(prefix)}/sensors/load/"
    if not topic.startswith(base):
        return None
    ext_id = topic[len(base) :]
    return ext_id or None
