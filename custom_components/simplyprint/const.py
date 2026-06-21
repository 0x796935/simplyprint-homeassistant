"""Constants for the SimplyPrint integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "simplyprint"

# Default public API host. Self-hosted/enterprise deployments can override this.
DEFAULT_BASE_URL: Final = "https://api.simplyprint.io"

MANUFACTURER: Final = "SimplyPrint"
PANEL_URL: Final = "https://simplyprint.io/panel"

# Config entry keys
CONF_API_KEY: Final = "api_key"
CONF_COMPANY_ID: Final = "company_id"
CONF_BASE_URL: Final = "base_url"

# Options keys
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_ENABLE_STATISTICS: Final = "enable_statistics"
CONF_STATISTICS_DAYS: Final = "statistics_days"

# Defaults / bounds
DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 15
MAX_SCAN_INTERVAL: Final = 600
DEFAULT_ENABLE_STATISTICS: Final = False
DEFAULT_STATISTICS_DAYS: Final = 30

MIN_UPDATE_INTERVAL: Final = timedelta(seconds=MIN_SCAN_INTERVAL)

# Account-level device identifier suffix
ACCOUNT_DEVICE_PREFIX: Final = "account"
PRINTER_DEVICE_PREFIX: Final = "printer"

# Printer states reported by the API (raw states).
STATE_PRINTING: Final = "printing"
STATE_OPERATIONAL: Final = "operational"
STATE_PAUSED: Final = "paused"
STATE_PAUSING: Final = "pausing"
STATE_RESUMING: Final = "resuming"
STATE_CANCELLING: Final = "cancelling"
STATE_ERROR: Final = "error"
STATE_OFFLINE: Final = "offline"
STATE_DOWNLOADING: Final = "downloading"
STATE_UNKNOWN: Final = "unknown"

# All states we expose as enum options for the status sensor.
PRINTER_STATES: Final = [
    STATE_OPERATIONAL,
    STATE_PRINTING,
    STATE_PAUSED,
    STATE_PAUSING,
    STATE_RESUMING,
    STATE_CANCELLING,
    STATE_ERROR,
    STATE_OFFLINE,
    STATE_DOWNLOADING,
    "in_maintenance",
    STATE_UNKNOWN,
]

# Service names
SERVICE_PAUSE: Final = "pause"
SERVICE_RESUME: Final = "resume"
SERVICE_CANCEL: Final = "cancel"
SERVICE_CLEAR_BED: Final = "clear_bed"
SERVICE_SEND_GCODE: Final = "send_gcode"

# Service field names
ATTR_REASON: Final = "reason"
ATTR_COMMENT: Final = "comment"
ATTR_RETURN_TO_QUEUE: Final = "return_to_queue"
ATTR_RETURN_POSITION: Final = "return_position"
ATTR_SUCCESS: Final = "success"
ATTR_RATING: Final = "rating"
ATTR_GCODE: Final = "gcode"
ATTR_MACRO: Final = "macro"
