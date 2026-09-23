"""Modbus polling for the Chint power meter integration."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any

from pymodbus.client import AsyncModbusSerialClient, AsyncModbusTcpClient
from pymodbus.client.mixin import ModbusClientMixin
from pymodbus.exceptions import ModbusException

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_METER_TYPE,
    CONF_SLAVE_IDS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MODBUS_BAUDRATE,
    MODBUS_TIMEOUT,
    READ_TIMEOUT,
    MeterTypes,
)

_LOGGER = logging.getLogger(__name__)

_TYPE = ModbusClientMixin.DATATYPE

type ChintConfigEntry = ConfigEntry[ChintUpdateCoordinator]


@dataclass(frozen=True)
class RegisterGroup:
    """A block of holding registers fetched in a single Modbus request.

    ``keys`` maps the index of a *decoded* value (not a register offset) to the
    key it is stored under in the coordinator data. A FLOAT32 value spans two
    registers, so index 5 of a 12 register block is the register at
    ``address + 10``.
    """

    address: int
    count: int
    data_type: ModbusClientMixin.DATATYPE
    keys: Mapping[int, str]


# Configuration ("keyboard") registers, one signed word each. Identical on both
# meter variants; only the -H exposes the meter type and the on-board clock.
_CONFIG_KEYS = {0: "rev", 1: "ucode", 2: "clre", 3: "net", 6: "irat", 7: "urat"}

# Voltages, currents, active and reactive power. FLOAT32 on both variants; the
# non-H returns raw values that still need the scaling from the manual's
# conversion table, which is applied by the sensor platform.
_ELECTRICAL_KEYS = {
    0: "uab",
    1: "ubc",
    2: "uca",
    3: "ua",
    4: "ub",
    5: "uc",
    6: "ia",
    7: "ib",
    8: "ic",
    9: "pt",
    10: "pa",
    11: "pb",
    12: "pc",
    13: "qt",
    14: "qa",
    15: "qb",
    16: "qc",
}

_POWER_FACTOR_KEYS = {0: "pft", 1: "pfa", 2: "pfb", 3: "pfc"}

REGISTER_GROUPS_H: tuple[RegisterGroup, ...] = (
    RegisterGroup(0x0000, 12, _TYPE.UINT16, _CONFIG_KEYS | {11: "meter_type"}),
    # 0x002C protocol, 0x002D address, 0x002E baud rate, 0x002F-0x0034 clock.
    RegisterGroup(
        0x002C,
        9,
        _TYPE.UINT16,
        {
            0: "protocol",
            1: "addr",
            2: "baud",
            3: "secound",
            4: "minutes",
            5: "hour",
            6: "day",
            7: "month",
            8: "year",
        },
    ),
    RegisterGroup(0x2000, 0x22, _TYPE.FLOAT32, _ELECTRICAL_KEYS),
    RegisterGroup(0x202A, 8, _TYPE.FLOAT32, _POWER_FACTOR_KEYS),
    RegisterGroup(0x2044, 2, _TYPE.FLOAT32, {0: "freq"}),
    # Total active power demand. Read as its own block so that a meter which
    # does not implement it cannot take the frequency reading down with it.
    RegisterGroup(0x2050, 2, _TYPE.FLOAT32, {0: "dmpt"}),
    # The manual documents the active energy totals at 0x401E, but that block
    # returns invalid data on the -H variant; 0x4026 is what it answers with.
    RegisterGroup(0x4026, 12, _TYPE.FLOAT32, {0: "impep", 5: "expep"}),
    RegisterGroup(0x4032, 2, _TYPE.FLOAT32, {0: "q1eq"}),
    RegisterGroup(0x403C, 2, _TYPE.FLOAT32, {0: "q2eq"}),
    RegisterGroup(0x4046, 2, _TYPE.FLOAT32, {0: "q3eq"}),
    RegisterGroup(0x4050, 2, _TYPE.FLOAT32, {0: "q4eq"}),
)

REGISTER_GROUPS_CT: tuple[RegisterGroup, ...] = (
    RegisterGroup(0x0000, 12, _TYPE.UINT16, _CONFIG_KEYS),
    # The DTSU666/DTSU666-CT manual orders these differently from the -H:
    # 0x002C protocol, 0x002D baud rate, 0x002E address.
    RegisterGroup(0x002C, 9, _TYPE.UINT16, {0: "protocol", 1: "baud", 2: "addr"}),
    RegisterGroup(0x2000, 0x22, _TYPE.FLOAT32, _ELECTRICAL_KEYS),
    RegisterGroup(0x202A, 8, _TYPE.FLOAT32, _POWER_FACTOR_KEYS),
    RegisterGroup(0x2044, 2, _TYPE.FLOAT32, {0: "freq"}),
    # Primary side energy: 0x101E ImpEp, 0x1028 ExpEp (index 5 of this block).
    RegisterGroup(0x101E, 12, _TYPE.FLOAT32, {0: "impep", 5: "expep"}),
    RegisterGroup(0x1032, 2, _TYPE.FLOAT32, {0: "q1eq"}),
    RegisterGroup(0x103C, 2, _TYPE.FLOAT32, {0: "q2eq"}),
    RegisterGroup(0x1046, 2, _TYPE.FLOAT32, {0: "q3eq"}),
    RegisterGroup(0x1050, 2, _TYPE.FLOAT32, {0: "q4eq"}),
)


def build_unique_id(data: Mapping[str, Any]) -> str:
    """Return a stable unique id for the meter described by ``data``."""
    unit_id = data[CONF_SLAVE_IDS][0]
    if host := data.get(CONF_HOST):
        return f"{host}:{data[CONF_PORT]}:{unit_id}"
    return f"{data[CONF_PORT]}:{unit_id}"


def meter_model(meter_type: str) -> str:
    """Return the marketing name of a meter type."""
    if meter_type == MeterTypes.METER_TYPE_CT_3P:
        return "DTSU666"
    return "DTSU666-H"


class ChintUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll a Chint DTSU666 power meter over Modbus."""

    config_entry: ChintConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ChintConfigEntry) -> None:
        """Initialise the coordinator for a single meter."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.unique_id or entry.entry_id}",
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_UPDATE_INTERVAL)
            ),
        )
        self._client: AsyncModbusSerialClient | AsyncModbusTcpClient | None = None
        self._unit_id: int = entry.data[CONF_SLAVE_IDS][0]
        self._model = meter_model(entry.data[CONF_METER_TYPE])
        if entry.data[CONF_METER_TYPE] == MeterTypes.METER_TYPE_CT_3P:
            self._groups = REGISTER_GROUPS_CT
        else:
            self._groups = REGISTER_GROUPS_H

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this meter."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            name=self.config_entry.title,
            manufacturer="Chint",
            model=self._model,
        )

    async def _async_setup(self) -> None:
        """Create the Modbus client before the first refresh."""
        entry = self.config_entry
        port = entry.data[CONF_PORT]
        if host := entry.data.get(CONF_HOST):
            self._client = AsyncModbusTcpClient(
                host=host, port=port, timeout=MODBUS_TIMEOUT
            )
        else:
            self._client = AsyncModbusSerialClient(
                port=port,
                baudrate=MODBUS_BAUDRATE,
                bytesize=8,
                stopbits=1,
                parity="N",
                timeout=MODBUS_TIMEOUT,
            )

    async def async_close(self) -> None:
        """Close the Modbus connection."""
        if self._client is not None:
            # pymodbus closes synchronously, awaiting this returns None.
            self._client.close()
            self._client = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Read every register block the configured meter type exposes."""
        if self._client is None:
            raise UpdateFailed("The Modbus client was not set up")

        try:
            async with asyncio.timeout(READ_TIMEOUT):
                if not self._client.connected and not await self._client.connect():
                    raise UpdateFailed(f"Could not connect to {self.name}")
                return await self._async_read_groups(self._client)
        except TimeoutError as err:
            # Drop the connection so the next poll starts from a clean state.
            self._client.close()
            raise UpdateFailed(f"Timeout while reading {self.name}") from err
        except ModbusException as err:
            self._client.close()
            raise UpdateFailed(
                f"Modbus error while reading {self.name}: {err}"
            ) from err

    async def _async_read_groups(
        self, client: AsyncModbusSerialClient | AsyncModbusTcpClient
    ) -> dict[str, Any]:
        """Read the register blocks one by one and decode them."""
        data: dict[str, Any] = {}
        rejected: list[str] = []

        for group in self._groups:
            result = await client.read_holding_registers(
                address=group.address, count=group.count, device_id=self._unit_id
            )
            if result.isError():
                # A meter that does not implement a block answers with an
                # exception response. Skip it instead of failing the whole poll.
                rejected.append(f"0x{group.address:04X}")
                continue

            decoded = client.convert_from_registers(
                result.registers, data_type=group.data_type
            )
            # A block that decodes to a single value is returned as a scalar.
            if not isinstance(decoded, list):
                decoded = [decoded]

            for index, key in group.keys.items():
                if index >= len(decoded):
                    _LOGGER.debug(
                        "Block 0x%04X decoded to %d values, no index %d for %s",
                        group.address,
                        len(decoded),
                        index,
                        key,
                    )
                    continue
                data[key] = decoded[index]

        if not data:
            raise UpdateFailed(
                f"{self.name} rejected every register block ({', '.join(rejected)})"
            )
        if rejected:
            _LOGGER.debug(
                "%s rejected the register blocks: %s", self.name, ", ".join(rejected)
            )
        return data
