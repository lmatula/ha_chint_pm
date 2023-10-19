from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import zip_longest
from typing import Any, Union

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ENERGY_KILO_WATT_HOUR,
    PERCENTAGE,
    POWER_VOLT_AMPERE_REACTIVE,
    POWER_WATT,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_UPDATE_COORDINATORS,
    DOMAIN,
    CONF_PHASE_MODE,
    CONF_METER_TYPE,
    PHMODE_3P4W,
    PHMODE_3P3W,
    MeterTypes,
)

from . import ChintDxsuDevice, ChintUpdateCoordinator


@dataclass
class ChintPmSensorEntityDescription(SensorEntityDescription):
    """Chint PM Sensor Entity."""

    phase_mode_relevant: str | None = None
    address: int | None = None
    count: int | None = None
    data_type: str | None = None
    value_conversion_function: Callable[[Any], str] | None = None


SENSOR_DESCRIPTIONS: tuple[ChintPmSensorEntityDescription, ...] = (
    ChintPmSensorEntityDescription(
        key="rev",
        name="Version",
        icon="mdi:package-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ChintPmSensorEntityDescription(
        key="ucode",
        name="Programming password codE",
        icon="mdi:form-textbox-password",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ChintPmSensorEntityDescription(
        key="clre",
        name="Electric energy zero clearing CLr.E(1:zero clearing)",
        icon="mdi:tune-vertical-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ChintPmSensorEntityDescription(
        key="net",
        name="Connection mode net",
        icon="mdi:tune-vertical-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ChintPmSensorEntityDescription(
        key="irat",
        name="Current Transformer Ratio",
        icon="mdi:information-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ChintPmSensorEntityDescription(
        key="urat",
        name="Potential Transformer Ratio(*)",
        icon="mdi:information-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: value * 0.1,
    ),
    ChintPmSensorEntityDescription(
        key="meter_type",
        name="Meter type",
        icon="mdi:format-list-bulleted-type",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ChintPmSensorEntityDescription(
        key="protocol",
        name="Protocol changing-over",
        icon="mdi:electric-switch-closed",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ChintPmSensorEntityDescription(
        key="addr",
        name="Communication address Addr",
        icon="mdi:map-marker-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ChintPmSensorEntityDescription(
        key="baud",
        name="Communication baud rate bAud",
        icon="mdi:speedometer",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ChintPmSensorEntityDescription(
        key="secound",
        name="Second",
        icon="mdi:clock-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ChintPmSensorEntityDescription(
        key="minutes",
        name="Minute",
        icon="mdi:clock-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ChintPmSensorEntityDescription(
        key="hour",
        name="Hour",
        icon="mdi:clock-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ChintPmSensorEntityDescription(
        key="day",
        name="Day",
        icon="mdi:calendar-month-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ChintPmSensorEntityDescription(
        key="month",
        name="Month",
        icon="mdi:calendar-month-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ChintPmSensorEntityDescription(
        key="year",
        name="Year",
        icon="mdi:calendar-month-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # electricity measurements
    ChintPmSensorEntityDescription(
        key="uab",
        name="Line AB-line voltage",
        phase_mode_relevant=PHMODE_3P3W,
        icon="mdi:sine-wave",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="ubc",
        name="Line BC-line voltage",
        phase_mode_relevant=PHMODE_3P3W,
        icon="mdi:sine-wave",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="uca",
        name="Line CA-line voltage",
        phase_mode_relevant=PHMODE_3P3W,
        icon="mdi:sine-wave",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="ua",
        name="A-phase voltage",
        phase_mode_relevant=PHMODE_3P4W,
        icon="mdi:sine-wave",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="ub",
        name="B-phase voltage",
        phase_mode_relevant=PHMODE_3P4W,
        icon="mdi:sine-wave",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="uc",
        name="C-phase voltage",
        phase_mode_relevant=PHMODE_3P4W,
        icon="mdi:sine-wave",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="ia",
        name="A phase current",
        icon="mdi:current-ac",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="ib",
        name="B phase current",
        phase_mode_relevant=PHMODE_3P4W,
        icon="mdi:current-ac",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="ic",
        name="C phase current",
        icon="mdi:current-ac",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="pt",
        name="Conjunction active power",
        icon="mdi:flash",
        native_unit_of_measurement=POWER_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="pa",
        name="A phase active power",
        icon="mdi:flash",
        native_unit_of_measurement=POWER_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="pb",
        name="B phase active power",
        phase_mode_relevant=PHMODE_3P4W,
        icon="mdi:flash",
        native_unit_of_measurement=POWER_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="pc",
        name="C phase active power",
        icon="mdi:flash",
        native_unit_of_measurement=POWER_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="qt",
        name="Conjunction reactive power",
        icon="mdi:lightning-bolt-circle",
        native_unit_of_measurement=POWER_VOLT_AMPERE_REACTIVE,
        device_class=SensorDeviceClass.REACTIVE_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="qa",
        name="A phase reactive power",
        icon="mdi:lightning-bolt-circle",
        native_unit_of_measurement=POWER_VOLT_AMPERE_REACTIVE,
        device_class=SensorDeviceClass.REACTIVE_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="qb",
        name="B phase reactive power",
        phase_mode_relevant=PHMODE_3P4W,
        icon="mdi:lightning-bolt-circle",
        native_unit_of_measurement=POWER_VOLT_AMPERE_REACTIVE,
        device_class=SensorDeviceClass.REACTIVE_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="qc",
        name="C phase reactive power",
        icon="mdi:lightning-bolt-circle",
        native_unit_of_measurement=POWER_VOLT_AMPERE_REACTIVE,
        device_class=SensorDeviceClass.REACTIVE_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="pft",
        name="Conjunction power factor",
        icon="mdi:math-cos",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="pfa",
        name="A phase power factor",
        phase_mode_relevant=PHMODE_3P4W,
        icon="mdi:math-cos",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="pfb",
        name="B phase power factor",
        phase_mode_relevant=PHMODE_3P4W,
        icon="mdi:math-cos",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="pfc",
        name="C phase power factor",
        phase_mode_relevant=PHMODE_3P4W,
        icon="mdi:math-cos",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="freq",
        name="Frequency",
        icon="mdi:wave",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="dmpt",
        name="Total active power demand",
        icon="mdi:home-lightning-bolt-outline",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="impep",
        name="Positive active total energy",
        icon="mdi:transmission-tower-export",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="expep",
        name="Negative active total energy",
        icon="mdi:transmission-tower-import",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="q1eq",
        name="Quadrant I reactive total energy",
        icon="mdi:",
        native_unit_of_measurement="kVarh",
        device_class=None,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="q2eq",
        name="Quadrant II reactive total energy",
        icon="mdi:",
        native_unit_of_measurement="kVarh",
        device_class=None,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="q3eq",
        name="Quadrant III reactive total energy",
        icon="mdi:",
        native_unit_of_measurement="kVarh",
        device_class=None,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="q4eq",
        name="Quadrant IV reactive total energy",
        icon="mdi:",
        native_unit_of_measurement="kVarh",
        device_class=None,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: round(value, 2),
    ),
)

SENSOR_DESCRIPTIONS_TYPE_NORMAL: tuple[ChintPmSensorEntityDescription, ...] = (
    ChintPmSensorEntityDescription(
        key="rev",
        name="Version",
        icon="mdi:package-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ChintPmSensorEntityDescription(
        key="ucode",
        name="Programming password codE",
        icon="mdi:form-textbox-password",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ChintPmSensorEntityDescription(
        key="clre",
        name="Electric energy zero clearing CLr.E(1:zero clearing)",
        icon="mdi:tune-vertical-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ChintPmSensorEntityDescription(
        key="net",
        name="Connection mode net",
        icon="mdi:tune-vertical-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ChintPmSensorEntityDescription(
        key="irat",
        name="Current Transformer Ratio",
        icon="mdi:information-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ChintPmSensorEntityDescription(
        key="urat",
        name="Potential Transformer Ratio(*)",
        icon="mdi:information-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: value * 0.1,
    ),
    ChintPmSensorEntityDescription(
        key="protocol",
        name="Protocol changing-over",
        icon="mdi:electric-switch-closed",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ChintPmSensorEntityDescription(
        key="addr",
        name="Communication address Addr",
        icon="mdi:map-marker-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ChintPmSensorEntityDescription(
        key="baud",
        name="Communication baud rate bAud",
        icon="mdi:speedometer",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # electricity measurements
    ChintPmSensorEntityDescription(
        key="uab",
        name="Line AB-line voltage",
        phase_mode_relevant=PHMODE_3P3W,
        icon="mdi:sine-wave",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: round(value * 0.1, 2),
    ),
    ChintPmSensorEntityDescription(
        key="ubc",
        name="Line BC-line voltage",
        phase_mode_relevant=PHMODE_3P3W,
        icon="mdi:sine-wave",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: round(value * 0.1, 2),
    ),
    ChintPmSensorEntityDescription(
        key="uca",
        name="Line CA-line voltage",
        phase_mode_relevant=PHMODE_3P3W,
        icon="mdi:sine-wave",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: round(value * 0.1, 2),
    ),
    ChintPmSensorEntityDescription(
        key="ua",
        name="A-phase voltage",
        phase_mode_relevant=PHMODE_3P4W,
        icon="mdi:sine-wave",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value * 0.1, 2),
    ),
    ChintPmSensorEntityDescription(
        key="ub",
        name="B-phase voltage",
        phase_mode_relevant=PHMODE_3P4W,
        icon="mdi:sine-wave",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value * 0.1, 2),
    ),
    ChintPmSensorEntityDescription(
        key="uc",
        name="C-phase voltage",
        phase_mode_relevant=PHMODE_3P4W,
        icon="mdi:sine-wave",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value * 0.1, 2),
    ),
    ChintPmSensorEntityDescription(
        key="ia",
        name="A phase current",
        icon="mdi:current-ac",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value * 0.001, 2),
    ),
    ChintPmSensorEntityDescription(
        key="ib",
        name="B phase current",
        phase_mode_relevant=PHMODE_3P4W,
        icon="mdi:current-ac",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value * 0.001, 2),
    ),
    ChintPmSensorEntityDescription(
        key="ic",
        name="C phase current",
        icon="mdi:current-ac",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value * 0.001, 2),
    ),
    ChintPmSensorEntityDescription(
        key="pt",
        name="Conjunction active power",
        icon="mdi:flash",
        native_unit_of_measurement=POWER_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value * 0.1, 2),
    ),
    ChintPmSensorEntityDescription(
        key="pa",
        name="A phase active power",
        icon="mdi:flash",
        native_unit_of_measurement=POWER_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value * 0.1, 2),
    ),
    ChintPmSensorEntityDescription(
        key="pb",
        name="B phase active power",
        phase_mode_relevant=PHMODE_3P4W,
        icon="mdi:flash",
        native_unit_of_measurement=POWER_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value * 0.1, 2),
    ),
    ChintPmSensorEntityDescription(
        key="pc",
        name="C phase active power",
        icon="mdi:flash",
        native_unit_of_measurement=POWER_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value * 0.1, 2),
    ),
    ChintPmSensorEntityDescription(
        key="qt",
        name="Conjunction reactive power",
        icon="mdi:lightning-bolt-circle",
        native_unit_of_measurement=POWER_VOLT_AMPERE_REACTIVE,
        device_class=SensorDeviceClass.REACTIVE_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value * 0.1, 2),
    ),
    ChintPmSensorEntityDescription(
        key="qa",
        name="A phase reactive power",
        icon="mdi:lightning-bolt-circle",
        native_unit_of_measurement=POWER_VOLT_AMPERE_REACTIVE,
        device_class=SensorDeviceClass.REACTIVE_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value * 0.1, 2),
    ),
    ChintPmSensorEntityDescription(
        key="qb",
        name="B phase reactive power",
        phase_mode_relevant=PHMODE_3P4W,
        icon="mdi:lightning-bolt-circle",
        native_unit_of_measurement=POWER_VOLT_AMPERE_REACTIVE,
        device_class=SensorDeviceClass.REACTIVE_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value * 0.1, 2),
    ),
    ChintPmSensorEntityDescription(
        key="qc",
        name="C phase reactive power",
        icon="mdi:lightning-bolt-circle",
        native_unit_of_measurement=POWER_VOLT_AMPERE_REACTIVE,
        device_class=SensorDeviceClass.REACTIVE_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value * 0.1, 2),
    ),
    ChintPmSensorEntityDescription(
        key="pft",
        name="Conjunction power factor",
        icon="mdi:math-cos",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: round(value * 0.001, 2),
    ),
    ChintPmSensorEntityDescription(
        key="pfa",
        name="A phase power factor",
        phase_mode_relevant=PHMODE_3P4W,
        icon="mdi:math-cos",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: round(value * 0.001, 2),
    ),
    ChintPmSensorEntityDescription(
        key="pfb",
        name="B phase power factor",
        phase_mode_relevant=PHMODE_3P4W,
        icon="mdi:math-cos",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: round(value * 0.001, 2),
    ),
    ChintPmSensorEntityDescription(
        key="pfc",
        name="C phase power factor",
        phase_mode_relevant=PHMODE_3P4W,
        icon="mdi:math-cos",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: round(value * 0.001, 2),
    ),
    ChintPmSensorEntityDescription(
        key="freq",
        name="Frequency",
        icon="mdi:wave",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value * 0.01, 2),
    ),
    ChintPmSensorEntityDescription(
        key="impep",
        name="Positive active total energy",
        icon="mdi:transmission-tower-export",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="expep",
        name="Negative active total energy",
        icon="mdi:transmission-tower-import",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=True,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="q1eq",
        name="Quadrant I reactive total energy",
        icon="mdi:",
        native_unit_of_measurement="kVarh",
        device_class=None,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="q2eq",
        name="Quadrant II reactive total energy",
        icon="mdi:",
        native_unit_of_measurement="kVarh",
        device_class=None,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="q3eq",
        name="Quadrant III reactive total energy",
        icon="mdi:",
        native_unit_of_measurement="kVarh",
        device_class=None,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: round(value, 2),
    ),
    ChintPmSensorEntityDescription(
        key="q4eq",
        name="Quadrant IV reactive total energy",
        icon="mdi:",
        native_unit_of_measurement="kVarh",
        device_class=None,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        value_conversion_function=lambda value: round(value, 2),
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Add pm entry."""

    update_coordinators: list[ChintUpdateCoordinator] = hass.data[DOMAIN][
        entry.entry_id
    ][DATA_UPDATE_COORDINATORS]

    entities_to_add: list[SensorEntity] = []
    for idx, (update_coordinator) in enumerate(zip_longest(update_coordinators)):
        # device = update_coordinators[idx].device
        device_info = update_coordinator[idx].device_info

        match entry.data[CONF_METER_TYPE]:
            case MeterTypes.METER_TYPE_CT_3P:
                used_sensor_description = SENSOR_DESCRIPTIONS_TYPE_NORMAL
            case _:
                used_sensor_description = SENSOR_DESCRIPTIONS

        for entity_description in used_sensor_description:
            if entity_description.phase_mode_relevant == entry.data[CONF_PHASE_MODE]:
                entity_description.entity_registry_enabled_default = True

            sensor = ChintPMModbusSensor(
                update_coordinator[idx], entity_description, device_info
            )
            # TODO: itt kell hozzá adnom a modbus cimeket
            # await update_coordinator[idx].push_sensor_read(
            #   entity_description.address,
            #   entity_description.count,
            #   entity_description.data_type,
            # )
            entities_to_add.append(sensor)

    async_add_entities(entities_to_add, True)


class ChintPMModbusSensor(CoordinatorEntity, ChintDxsuDevice, SensorEntity):
    """power meter sensor"""

    def __init__(
        self,
        coordinator: ChintUpdateCoordinator,
        description: ChintPmSensorEntityDescription,
        device_info,
    ):
        """Batched Huawei Solar Sensor Entity constructor."""
        super().__init__(coordinator)

        self.coordinator = coordinator
        self.entity_description = description

        self._attr_device_info = device_info
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.entity_description.key in self.coordinator.device.data:
            value = self.coordinator.device.data[self.entity_description.key]
            if self.entity_description.value_conversion_function:
                value = self.entity_description.value_conversion_function(value)

            self._attr_native_value = value
            self.async_write_ha_state()
