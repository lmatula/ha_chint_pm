"""Constants for the Chint pm integration."""
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfFrequency,
)
from homeassistant.helpers.entity import EntityCategory

from datetime import timedelta

DOMAIN = "chint_pm"
DEFAULT_PORT = 502
DEFAULT_SLAVE_ID = 11
DEFAULT_SERIAL_SLAVE_ID = 11
DEFAULT_USERNAME = ""
DEFAULT_PASSWORD = ""

CONF_SLAVE_IDS = "slave_ids"
CONF_PHASE_MODE = "phase_mode"
CONF_METER_TYPE = "meter_type"

DATA_UPDATE_COORDINATORS = "update_coordinators"

UPDATE_INTERVAL = timedelta(seconds=15)

PHMODE_3P4W = "3P4W"
PHMODE_3P3W = "3P3W"


class MeterTypes:
    METER_TYPE_H_3P = "1"
    METER_TYPE_CT_3P = "2"
