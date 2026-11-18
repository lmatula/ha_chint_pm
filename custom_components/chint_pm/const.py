"""Constants for the Chint power meter integration."""

from __future__ import annotations

from enum import StrEnum

DOMAIN = "chint_pm"

# Config entry schema version, shared by the config flow and the migration.
CONFIG_ENTRY_VERSION = 4

DEFAULT_PORT = 502
DEFAULT_SLAVE_ID = 11
DEFAULT_SERIAL_SLAVE_ID = 11
# The DTSU666-20 (sold by Sungrow) ships with Modbus address 1.
DEFAULT_SLAVE_ID_20 = 1

CONF_SLAVE_IDS = "slave_ids"
CONF_PHASE_MODE = "phase_mode"
CONF_METER_TYPE = "meter_type"
# DTSU666-20 only: also poll the second current channel (CT2). Kept in the
# config entry options so it can be changed after setup.
CONF_SECOND_CHANNEL = "second_channel"

CONNECTION_SERIAL = "serial"
CONNECTION_NETWORK = "network"

# Default polling interval in seconds; user-configurable via the options flow.
DEFAULT_UPDATE_INTERVAL = 15
MIN_UPDATE_INTERVAL = 1
MAX_UPDATE_INTERVAL = 3600

# Serial line settings the meter ships with (see the operation manual, ModBus-RTU
# is 9600 8N1 by default).
MODBUS_BAUDRATE = 9600
# Per-request timeout handed to pymodbus.
MODBUS_TIMEOUT = 5
# Upper bound for a complete poll of every register block.
READ_TIMEOUT = 30

PHMODE_3P4W = "3P4W"
PHMODE_3P3W = "3P3W"


class MeterTypes(StrEnum):
    """Supported meter variants.

    The values are stored in the config entry, so they must not change.
    """

    METER_TYPE_H_3P = "1"
    METER_TYPE_CT_3P = "2"
    # Dual channel DTSU666-20 (Sungrow), see docs/DTSU666-20_register_map.md.
    METER_TYPE_20_3P = "3"
