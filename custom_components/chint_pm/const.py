"""Constants for the Chint power meter integration."""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum

DOMAIN = "chint_pm"

# Config entry schema version, shared by the config flow and the migration.
CONFIG_ENTRY_VERSION = 4

DEFAULT_PORT = 502
DEFAULT_SLAVE_ID = 11
DEFAULT_SERIAL_SLAVE_ID = 11

CONF_SLAVE_IDS = "slave_ids"
CONF_PHASE_MODE = "phase_mode"
CONF_METER_TYPE = "meter_type"

CONNECTION_SERIAL = "serial"
CONNECTION_NETWORK = "network"

UPDATE_INTERVAL = timedelta(seconds=15)

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
