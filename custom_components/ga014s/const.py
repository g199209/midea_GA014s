"""Constants for the GA014s integration."""
from __future__ import annotations

import logging

DOMAIN = "ga014s"
LOGGER = logging.getLogger(f"custom_components.{DOMAIN}")

CONF_HOST = "host"
DEFAULT_NAME = "Midea GA014s"

# Months (1-12) treated as winter. During these months turn_on selects heating;
# otherwise it selects cooling. This matches the central system's seasonal
# master mode and avoids the mode-conflict fault a blind guess can trigger.
CONF_WINTER_MONTHS = "winter_months"
DEFAULT_WINTER_MONTHS = [11, 12, 1, 2, 3, 4]

HVAC_MODE_MAP = {
    0: "off",
    1: "fan_only",
    2: "cool",
    3: "heat",
    4: "auto",
    5: "dry",
}
HVAC_MODE_REVERSE = {v: k for k, v in HVAC_MODE_MAP.items()}

FAN_MODE_MAP = {
    1: "low",
    2: "low_medium",
    3: "medium",
    4: "medium_high",
    5: "high",
    6: "higher",
    7: "max",
    8: "auto",
}
FAN_MODE_REVERSE = {v: k for k, v in FAN_MODE_MAP.items()}
FAN_MODES = list(FAN_MODE_MAP.values())

SWING_MODE_MAP = {0: "off", 1: "on"}
SWING_MODE_REVERSE = {v: k for k, v in SWING_MODE_MAP.items()}

PRESET_NONE = "none"
PRESET_AUX_HEAT = "aux_heat"
PRESET_MODES = [PRESET_NONE, PRESET_AUX_HEAT]

MIN_TEMP = 17
MAX_TEMP = 30
