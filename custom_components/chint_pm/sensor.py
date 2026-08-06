"""Sensor platform for the Chint power meter integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfReactiveEnergy,
    UnitOfReactivePower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_METER_TYPE,
    CONF_PHASE_MODE,
    PHMODE_3P3W,
    PHMODE_3P4W,
    MeterTypes,
)
from .coordinator import ChintConfigEntry, ChintUpdateCoordinator

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class ChintSensorEntityDescription(SensorEntityDescription):
    """Describes a value read from a Chint power meter."""

    # Applied to the raw register value; the non-H meter reports unscaled
    # integers that the manual's conversion table turns into SI units.
    value_fn: Callable[[float], float] | None = None
    # Enable this sensor by default when the meter is wired in this mode.
    phase_mode_relevant: str | None = None


def _diagnostic(
    key: str, *, value_fn: Callable[[float], float] | None = None
) -> ChintSensorEntityDescription:
    """Describe a meter configuration register."""
    return ChintSensorEntityDescription(
        key=key,
        translation_key=key,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=value_fn,
    )


def _measurement(
    key: str,
    *,
    device_class: SensorDeviceClass,
    unit: str | None = None,
    scale: float = 1.0,
    enabled: bool = True,
    phase_mode: str | None = None,
    state_class: SensorStateClass = SensorStateClass.MEASUREMENT,
) -> ChintSensorEntityDescription:
    """Describe a measured value."""
    return ChintSensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=device_class,
        native_unit_of_measurement=unit,
        state_class=state_class,
        entity_registry_enabled_default=enabled,
        phase_mode_relevant=phase_mode,
        suggested_display_precision=2,
        value_fn=None if scale == 1.0 else lambda value, scale=scale: value * scale,
    )


def _electrical_sensors(
    *,
    voltage: float,
    current: float,
    power: float,
    power_factor: float,
    frequency: float,
) -> tuple[ChintSensorEntityDescription, ...]:
    """Describe the sensors both meter variants share.

    The arguments are the per-variant scaling factors for the raw registers.
    """
    return (
        _measurement(
            "uab",
            device_class=SensorDeviceClass.VOLTAGE,
            unit=UnitOfElectricPotential.VOLT,
            scale=voltage,
            enabled=False,
            phase_mode=PHMODE_3P3W,
        ),
        _measurement(
            "ubc",
            device_class=SensorDeviceClass.VOLTAGE,
            unit=UnitOfElectricPotential.VOLT,
            scale=voltage,
            enabled=False,
            phase_mode=PHMODE_3P3W,
        ),
        _measurement(
            "uca",
            device_class=SensorDeviceClass.VOLTAGE,
            unit=UnitOfElectricPotential.VOLT,
            scale=voltage,
            enabled=False,
            phase_mode=PHMODE_3P3W,
        ),
        _measurement(
            "ua",
            device_class=SensorDeviceClass.VOLTAGE,
            unit=UnitOfElectricPotential.VOLT,
            scale=voltage,
            phase_mode=PHMODE_3P4W,
        ),
        _measurement(
            "ub",
            device_class=SensorDeviceClass.VOLTAGE,
            unit=UnitOfElectricPotential.VOLT,
            scale=voltage,
            phase_mode=PHMODE_3P4W,
        ),
        _measurement(
            "uc",
            device_class=SensorDeviceClass.VOLTAGE,
            unit=UnitOfElectricPotential.VOLT,
            scale=voltage,
            phase_mode=PHMODE_3P4W,
        ),
        _measurement(
            "ia",
            device_class=SensorDeviceClass.CURRENT,
            unit=UnitOfElectricCurrent.AMPERE,
            scale=current,
        ),
        _measurement(
            "ib",
            device_class=SensorDeviceClass.CURRENT,
            unit=UnitOfElectricCurrent.AMPERE,
            scale=current,
            phase_mode=PHMODE_3P4W,
        ),
        _measurement(
            "ic",
            device_class=SensorDeviceClass.CURRENT,
            unit=UnitOfElectricCurrent.AMPERE,
            scale=current,
        ),
        _measurement(
            "pt",
            device_class=SensorDeviceClass.POWER,
            unit=UnitOfPower.WATT,
            scale=power,
        ),
        _measurement(
            "pa",
            device_class=SensorDeviceClass.POWER,
            unit=UnitOfPower.WATT,
            scale=power,
        ),
        _measurement(
            "pb",
            device_class=SensorDeviceClass.POWER,
            unit=UnitOfPower.WATT,
            scale=power,
            phase_mode=PHMODE_3P4W,
        ),
        _measurement(
            "pc",
            device_class=SensorDeviceClass.POWER,
            unit=UnitOfPower.WATT,
            scale=power,
        ),
        _measurement(
            "qt",
            device_class=SensorDeviceClass.REACTIVE_POWER,
            unit=UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
            scale=power,
        ),
        _measurement(
            "qa",
            device_class=SensorDeviceClass.REACTIVE_POWER,
            unit=UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
            scale=power,
        ),
        _measurement(
            "qb",
            device_class=SensorDeviceClass.REACTIVE_POWER,
            unit=UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
            scale=power,
            phase_mode=PHMODE_3P4W,
        ),
        _measurement(
            "qc",
            device_class=SensorDeviceClass.REACTIVE_POWER,
            unit=UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
            scale=power,
        ),
        _measurement(
            "pft",
            device_class=SensorDeviceClass.POWER_FACTOR,
            scale=power_factor,
            enabled=False,
        ),
        _measurement(
            "pfa",
            device_class=SensorDeviceClass.POWER_FACTOR,
            scale=power_factor,
            enabled=False,
            phase_mode=PHMODE_3P4W,
        ),
        _measurement(
            "pfb",
            device_class=SensorDeviceClass.POWER_FACTOR,
            scale=power_factor,
            enabled=False,
            phase_mode=PHMODE_3P4W,
        ),
        _measurement(
            "pfc",
            device_class=SensorDeviceClass.POWER_FACTOR,
            scale=power_factor,
            enabled=False,
            phase_mode=PHMODE_3P4W,
        ),
        _measurement(
            "freq",
            device_class=SensorDeviceClass.FREQUENCY,
            unit=UnitOfFrequency.HERTZ,
            scale=frequency,
        ),
    )


def _energy_sensors() -> tuple[ChintSensorEntityDescription, ...]:
    """Describe the energy totals, which both variants report in kWh/kvarh."""
    return (
        _measurement(
            "impep",
            device_class=SensorDeviceClass.ENERGY,
            unit=UnitOfEnergy.KILO_WATT_HOUR,
            state_class=SensorStateClass.TOTAL_INCREASING,
        ),
        _measurement(
            "expep",
            device_class=SensorDeviceClass.ENERGY,
            unit=UnitOfEnergy.KILO_WATT_HOUR,
            state_class=SensorStateClass.TOTAL_INCREASING,
        ),
        *(
            _measurement(
                key,
                device_class=SensorDeviceClass.REACTIVE_ENERGY,
                unit=UnitOfReactiveEnergy.KILO_VOLT_AMPERE_REACTIVE_HOUR,
                state_class=SensorStateClass.TOTAL_INCREASING,
                enabled=False,
            )
            for key in ("q1eq", "q2eq", "q3eq", "q4eq")
        ),
    )


# The -H variant reports every measurement as a ready to use float.
SENSOR_DESCRIPTIONS_H: tuple[ChintSensorEntityDescription, ...] = (
    _diagnostic("rev"),
    _diagnostic("ucode"),
    _diagnostic("clre"),
    _diagnostic("net"),
    _diagnostic("irat"),
    # 1-9999 represents a ratio of 0.1-999.9.
    _diagnostic("urat", value_fn=lambda value: value * 0.1),
    _diagnostic("meter_type"),
    _diagnostic("protocol"),
    _diagnostic("addr"),
    _diagnostic("baud"),
    _diagnostic("secound"),
    _diagnostic("minutes"),
    _diagnostic("hour"),
    _diagnostic("day"),
    _diagnostic("month"),
    _diagnostic("year"),
    *_electrical_sensors(
        voltage=1.0, current=1.0, power=1.0, power_factor=1.0, frequency=1.0
    ),
    _measurement("dmpt", device_class=SensorDeviceClass.POWER, unit=UnitOfPower.WATT),
    *_energy_sensors(),
)

# The non-H variant needs the scaling from the manual's conversion table.
SENSOR_DESCRIPTIONS_CT: tuple[ChintSensorEntityDescription, ...] = (
    _diagnostic("rev"),
    _diagnostic("ucode"),
    _diagnostic("clre"),
    _diagnostic("net"),
    _diagnostic("irat"),
    _diagnostic("urat", value_fn=lambda value: value * 0.1),
    _diagnostic("protocol"),
    _diagnostic("addr"),
    _diagnostic("baud"),
    *_electrical_sensors(
        voltage=0.1, current=0.001, power=0.1, power_factor=0.001, frequency=0.01
    ),
    *_energy_sensors(),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChintConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the power meter sensors."""
    coordinator = entry.runtime_data

    if entry.data[CONF_METER_TYPE] == MeterTypes.METER_TYPE_CT_3P:
        descriptions = SENSOR_DESCRIPTIONS_CT
    else:
        descriptions = SENSOR_DESCRIPTIONS_H

    phase_mode = entry.data.get(CONF_PHASE_MODE)
    async_add_entities(
        ChintPowerMeterSensor(coordinator, description, phase_mode)
        for description in descriptions
    )


class ChintPowerMeterSensor(CoordinatorEntity[ChintUpdateCoordinator], SensorEntity):
    """A single value read from a Chint power meter."""

    entity_description: ChintSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ChintUpdateCoordinator,
        description: ChintSensorEntityDescription,
        phase_mode: str | None,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"
        if description.phase_mode_relevant == phase_mode:
            self._attr_entity_registry_enabled_default = True

    @property
    def available(self) -> bool:
        """Return True when the meter reported this value."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.entity_description.key in self.coordinator.data
        )

    @property
    def native_value(self) -> float | None:
        """Return the value of the sensor."""
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.get(self.entity_description.key)
        if value is None:
            return None
        if self.entity_description.value_fn is not None:
            return self.entity_description.value_fn(value)
        return value
