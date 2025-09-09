"""The Chint pm  Integration."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta
import logging
import threading
from typing import TypeVar

# Use asyncio.timeout instead of async_timeout
from pymodbus.client import AsyncModbusSerialClient, AsyncModbusTcpClient
from pymodbus.exceptions import ModbusIOException

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_METER_TYPE,
    CONF_SLAVE_IDS,
    DATA_UPDATE_COORDINATORS,
    DOMAIN,
    UPDATE_INTERVAL,
    MeterTypes,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
]

T = TypeVar("T")


class ChintDxsuDevice:
    """Chint pm device object"""

    def __init__(self, hass, entry, scan_interval) -> None:
        """Initialize the Modbus hub."""
        self._hass = hass
        self._entry = entry
        self._lock = threading.Lock()
        self._scan_interval = scan_interval
        self._unsub_interval_method = None
        self._sensors = []
        self.data = {}

    async def update(self, client, unit_id):
        """update sensors"""
        match self._entry.data[CONF_METER_TYPE]:
            case MeterTypes.METER_TYPE_CT_3P:
                await self.read_values_type_normal(client, unit_id)
            case _:
                await self.read_values(client, unit_id)

    async def read_values(self, client, unit_id):
        """read modbus value groups"""

        async def read_header(registers):
            decoder = client.convert_from_registers(
                registers, data_type=client.DATATYPE.UINT16
            )
            # REV verison
            self.data["rev"] = decoder[0]
            # UCode Programming password codE
            self.data["ucode"] = decoder[1]
            # ClrE Electric energy zero clearing CLr.E(1:zero clearing)
            self.data["clre"] = decoder[2]
            # net Selecting of the connection mode net(0:3P4W,1:3P3W)
            self.data["net"] = decoder[3]
            #  decoder.skip_bytes(2 * 2)
            # IrAt Current Transformer Ratio
            self.data["irat"] = decoder[6]
            # UrAt Potential Transformer Ratio(*)
            self.data["urat"] = decoder[7]
            # decoder.skip_bytes(3 * 2)
            # Meter type
            self.data["meter_type"] = decoder[11]

        async def read_header_proto(registers):
            decoder = client.convert_from_registers(
                registers, data_type=client.DATATYPE.UINT16
            )
            # Protocol Protocol changing-over
            self.data["protocol"] = decoder[0]
            # Addr Communication address Addr
            self.data["addr"] = decoder[1]
            # bAud Communication baud rate bAud
            self.data["baud"] = decoder[2]

            # Secound
            self.data["secound"] = decoder[3]
            # Minutes
            self.data["minutes"] = decoder[4]
            # Hour
            self.data["hour"] = decoder[5]
            # Day
            self.data["day"] = decoder[6]
            # Month
            self.data["month"] = decoder[7]
            # Year
            self.data["year"] = decoder[8]

        async def read_elecricity_power(registers):
            decoder = client.convert_from_registers(
                registers, data_type=client.DATATYPE.FLOAT32
            )

            # Uab Line -line voltage, the unit is V
            self.data["uab"] = decoder[0]
            # Ubc Line -line voltage, the unit is V
            self.data["ubc"] = decoder[1]
            # Uca Line -line voltage, the unit is V
            self.data["uca"] = decoder[2]

            # Ua Phase-phase voltage, the unit is V
            self.data["ua"] = decoder[3]
            # Ub Phase-phase voltaget, he unit is V
            self.data["ub"] = decoder[4]
            # Uc Phase-phase voltage, the unit is V
            self.data["uc"] = decoder[5]

            # Ia The data of three phase current,the unit is A
            self.data["ia"] = decoder[6]
            # Ib The data of three phase current,the unit is A
            self.data["ib"] = decoder[7]
            # Ic The data of three phase current,the unit is A
            self.data["ic"] = decoder[8]

            # Pt Conjunction active power，the unit is W
            self.data["pt"] = decoder[9]
            # Pa A phase active power，the unit is W
            self.data["pa"] = decoder[10]
            # Pb B phase active power，the unit is W (invalid when three phase three wire)
            self.data["pb"] = decoder[11]
            # Pc C phase active power，the unit is W
            self.data["pc"] = decoder[12]

            # Qt Conjunction reactive power，the unit is var
            self.data["qt"] = decoder[13]
            # Qa A phase reactive power， the unit is var
            self.data["qa"] = decoder[14]
            # Qb B phase reactive power， the unit is var (invalid when three phase three wire)
            self.data["qb"] = decoder[15]
            # Qc C phase reactive power， the unit is var
            self.data["qc"] = decoder[16]

        async def read_elecricity_factor(registers):
            decoder = client.convert_from_registers(
                registers, data_type=client.DATATYPE.FLOAT32
            )
            # PFt Conjunction power factor
            self.data["pft"] = decoder[0]
            # Pfa A phase power factor (invalid when three phase three wire)
            self.data["pfa"] = decoder[1]
            # PFb B phase power factor (invalid when three phase three wire)
            self.data["pfb"] = decoder[2]
            # PFc C phase power factor (invalid when three phase three wire)
            self.data["pfc"] = decoder[3]

        async def read_elecricity_other(registers):
            decoder = client.convert_from_registers(
                registers, data_type=client.DATATYPE.FLOAT32
            )
            # Freq Frequency
            self.data["freq"] = decoder[0]
            # decoder.skip_bytes(2 * 4)
            # DmPt Total active power demand
            self.data["dmpt"] = decoder[3]

        async def read_total(registers):
            decoder = client.convert_from_registers(
                registers, data_type=client.DATATYPE.FLOAT32
            )
            # ImpEp (current)positive active total energy
            self.data["impep"] = decoder[0]
            # decoder.skip_bytes(2 * 8)  # Skip to negative energy position
            # ExpEp (current)negative active total energy
            self.data["expep"] = decoder[5]

        async def read_quadrant_i(registers):
            decoder = client.convert_from_registers(
                registers, data_type=client.DATATYPE.FLOAT32
            )
            # (current) quadrant I reactive total energy
            self.data["q1eq"] = decoder[0]

        async def read_quadrant_ii(registers):
            decoder = client.convert_from_registers(
                registers, data_type=client.DATATYPE.FLOAT32
            )
            # (current) quadrant II reactive total energy
            self.data["q2eq"] = decoder[0]

        async def read_quadrant_iii(registers):
            decoder = client.convert_from_registers(
                registers, data_type=client.DATATYPE.FLOAT32
            )
            # (current) quadrant III reactive total energy
            self.data["q3eq"] = decoder[0]

        async def read_quadrant_iv(registers):
            decoder = client.convert_from_registers(
                registers, data_type=client.DATATYPE.FLOAT32
            )
            # (current) quadrant IV reactive total energy
            self.data["q4eq"] = decoder[0]

        if client.connected:
            header = await client.read_holding_registers(
                address=0x0, count=12, device_id=unit_id
            )
            header_proto = await client.read_holding_registers(
                address=0x2C, count=9, device_id=unit_id
            )
            elecricity_power = await client.read_holding_registers(
                address=0x2000, count=0x22, device_id=unit_id
            )
            elecricity_factor = await client.read_holding_registers(
                address=0x202A, count=8, device_id=unit_id
            )
            elecricity_other = await client.read_holding_registers(
                address=0x2044, count=8, device_id=unit_id
            )
            # documentation say address is 0x401e but this register contain invalid data, maybe only -H version?
            total = await client.read_holding_registers(
                address=0x4026, count=12, device_id=unit_id
            )
            # (current) quadrant I reactive total energy
            quadrant_i = await client.read_holding_registers(
                address=0x4032, count=2, device_id=unit_id
            )
            # (current) quadrant II reactive total energy
            quadrant_ii = await client.read_holding_registers(
                address=0x403C, count=2, device_id=unit_id
            )
            # (current) quadrant III reactive total energy
            quadrant_iii = await client.read_holding_registers(
                address=0x4046, count=2, device_id=unit_id
            )
            # (current) quadrant IV reactive total energy
            quadrant_iv = await client.read_holding_registers(
                address=0x4050, count=2, device_id=unit_id
            )

            out = await asyncio.gather(
                read_header(header.registers),
                read_header_proto(header_proto.registers),
                read_elecricity_power(elecricity_power.registers),
                read_elecricity_factor(elecricity_factor.registers),
                read_elecricity_other(elecricity_other.registers),
                read_total(total.registers),
                read_quadrant_i(quadrant_i.registers),
                read_quadrant_ii(quadrant_ii.registers),
                read_quadrant_iii(quadrant_iii.registers),
                read_quadrant_iv(quadrant_iv.registers),
                return_exceptions=True,
            )
            # print(out)

    async def read_values_type_normal(self, client, unit_id):
        """read modbus value groups"""

        async def read_header(registers):
            decoder = client.convert_from_registers(
                registers, data_type=client.DATATYPE.FLOAT32
            )
            # REV verison
            self.data["rev"] = decoder[0]
            # UCode Programming password codE
            self.data["ucode"] = decoder[1]
            # ClrE Electric energy zero clearing CLr.E(1:zero clearing)
            self.data["clre"] = decoder[2]
            # net Selecting of the connection mode net(0:3P4W,13P3W)
            self.data["net"] = decoder[3]
            decoder.skip_bytes(2 * 2)
            # IrAt Current Transformer Ratio
            self.data["irat"] = decoder[6]
            # UrAt Potential Transformer Ratio(*)
            self.data["urat"] = decoder[7]

        async def read_header_proto(registers):
            decoder = client.convert_from_registers(
                registers, data_type=client.DATATYPE.FLOAT32
            )
            # Protocol Protocol changing-over
            self.data["protocol"] = decoder[0]
            # Addr Communication address Addr
            self.data["baud"] = decoder[1]
            # bAud Communication baud rate bAud
            self.data["addr"] = decoder[2]

        async def read_elecricity_power(registers):
            decoder = client.convert_from_registers(
                registers, data_type=client.DATATYPE.FLOAT32
            )

            # Uab Line -line voltage, the unit is V
            self.data["uab"] = decoder[0]
            # Ubc Line -line voltage, the unit is V
            self.data["ubc"] = decoder[1]
            # Uca Line -line voltage, the unit is V
            self.data["uca"] = decoder[2]

            # Ua Phase-phase voltage, the unit is V
            self.data["ua"] = decoder[3]
            # Ub Phase-phase voltaget, he unit is V
            self.data["ub"] = decoder[4]
            # Uc Phase-phase voltage, the unit is V
            self.data["uc"] = decoder[5]

            # Ia The data of three phase current,the unit is A
            self.data["ia"] = decoder[6]
            # Ib The data of three phase current,the unit is A
            self.data["ib"] = decoder[7]
            # Ic The data of three phase current,the unit is A
            self.data["ic"] = decoder[8]

            # Pt Conjunction active power，the unit is W
            self.data["pt"] = decoder[9]
            # Pa A phase active power，the unit is W
            self.data["pa"] = decoder[10]
            # Pb B phase active power，the unit is W (invalid when three phase three wire)
            self.data["pb"] = decoder[11]
            # Pc C phase active power，the unit is W
            self.data["pc"] = decoder[12]

            # Qt Conjunction reactive power，the unit is var
            self.data["qt"] = decoder[13]
            # Qa A phase reactive power， the unit is var
            self.data["qa"] = decoder[14]
            # Qb B phase reactive power， the unit is var (invalid when three phase three wire)
            self.data["qb"] = decoder[15]
            # Qc C phase reactive power， the unit is var
            self.data["qc"] = decoder[16]

        async def read_elecricity_factor(registers):
            decoder = client.convert_from_registers(
                registers, data_type=client.DATATYPE.FLOAT32
            )
            # PFt Conjunction power factor
            self.data["pft"] = decoder[0]
            # Pfa A phase power factor (invalid when three phase three wire)
            self.data["pfa"] = decoder[1]
            # PFb B phase power factor (invalid when three phase three wire)
            self.data["pfb"] = decoder[2]
            # PFc C phase power factor (invalid when three phase three wire)
            self.data["pfc"] = decoder[3]

        async def read_elecricity_other(registers):
            decoder = client.convert_from_registers(
                registers, data_type=client.DATATYPE.FLOAT32
            )
            # Freq Frequency
            self.data["freq"] = decoder[0]

        async def read_total(registers):
            decoder = client.convert_from_registers(
                registers, data_type=client.DATATYPE.FLOAT32
            )
            # ImpEp (current)positive active total energy
            self.data["impep"] = decoder[0]
            decoder.skip_bytes(2 * 8)  # Skip to negative energy position
            # ExpEp (current)negative active total energy
            self.data["expep"] = decoder[5]

        async def read_quadrant_i(registers):
            decoder = client.convert_from_registers(
                registers, data_type=client.DATATYPE.FLOAT32
            )
            # (current) quadrant I reactive total energy
            self.data["q1eq"] = decoder[0]

        async def read_quadrant_ii(registers):
            # (current) quadrant II reactive total energy
            decoder = client.convert_from_registers(
                registers, data_type=client.DATATYPE.FLOAT32
            )
            self.data["q2eq"] = decoder[0]

        async def read_quadrant_iii(registers):
            # (current) quadrant III reactive total energy
            decoder = client.convert_from_registers(
                registers, data_type=client.DATATYPE.FLOAT32
            )
            self.data["q3eq"] = decoder[0]

        async def read_quadrant_iv(registers):
            decoder = client.convert_from_registers(
                registers, data_type=client.DATATYPE.FLOAT32
            )
            # (current) quadrant IV reactive total energy
            self.data["q4eq"] = decoder[0]

        if client.connected:
            header = await client.read_holding_registers(
                address=0x0, count=12, device_id=unit_id
            )
            header_proto = await client.read_holding_registers(
                address=0x2C, count=9, device_id=unit_id
            )
            elecricity_power = await client.read_holding_registers(
                address=0x2000, count=0x22, device_id=unit_id
            )
            elecricity_factor = await client.read_holding_registers(
                address=0x202A, count=8, device_id=unit_id
            )
            elecricity_other = await client.read_holding_registers(
                address=0x2044, count=8, device_id=unit_id
            )
            # documentation say address is 0x401e but this register contain invalid data, maybe only -H version?
            total = await client.read_holding_registers(
                address=0x101E, count=2, device_id=unit_id
            )
            # (current) quadrant I reactive total energy
            quadrant_i = await client.read_holding_registers(
                address=0x1032, count=2, device_id=unit_id
            )
            # (current) quadrant II reactive total energy
            quadrant_ii = await client.read_holding_registers(
                address=0x103C, count=2, device_id=unit_id
            )
            # (current) quadrant III reactive total energy
            quadrant_iii = await client.read_holding_registers(
                address=0x1046, count=2, device_id=unit_id
            )
            # (current) quadrant IV reactive total energy
            quadrant_iv = await client.read_holding_registers(
                address=0x1050, count=2, device_id=unit_id
            )

            await asyncio.gather(
                read_header(header.registers),
                read_header_proto(header_proto.registers),
                read_elecricity_power(elecricity_power.registers),
                read_elecricity_factor(elecricity_factor.registers),
                read_elecricity_other(elecricity_other.registers),
                read_total(total.registers),
                read_quadrant_i(quadrant_i.registers),
                read_quadrant_ii(quadrant_ii.registers),
                read_quadrant_iii(quadrant_iii.registers),
                read_quadrant_iv(quadrant_iv.registers),
                return_exceptions=True,
            )


class ChintUpdateCoordinator(DataUpdateCoordinator):
    """A specialised DataUpdateCoordinator for chint smart meter."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        device: ChintDxsuDevice,
        entry: ConfigEntry,
        update_interval: timedelta | None = None,
        update_method: Callable[[], Awaitable[T]] | None = None,
        request_refresh_debouncer: Debouncer | None = None,
    ) -> None:
        """Create a ChintUpdateCoordinator."""
        if entry.data[CONF_HOST] is None:
            port_host = ""
            port_name = str(entry.data[CONF_PORT])
        else:
            port_host = "".join(filter(str.isalnum, entry.data[CONF_HOST]))
            port_name = "".join(filter(str.isalnum, str(entry.data[CONF_PORT])))

        super().__init__(
            hass,
            logger,
            name=f"{port_host}_{port_name}_{entry.data[CONF_SLAVE_IDS][0]}_data_update_coordinator",
            update_interval=update_interval,
            update_method=update_method,
            request_refresh_debouncer=request_refresh_debouncer,
        )
        self.device = device
        self._client: AsyncModbusSerialClient | AsyncModbusTcpClient
        self._unit_id = entry.data[CONF_SLAVE_IDS][0]
        self._entry = entry

    async def push_sensor_read(self, address, count, data_type):
        # TODO: push device addresses to read
        await self._client.read_holding_registers(
            address=address, count=count, device_id=self._unit_id
        )
        self.device._sensors.append(1)

    async def create_client(self, port, host):
        """create one clinet object whole update cordinator"""
        try:
            if host is None:
                self._client = AsyncModbusSerialClient(
                    port=port,
                    baudrate=9600,
                    bytesize=8,
                    stopbits=1,
                    parity="N",
                )
            else:
                self._client = AsyncModbusTcpClient(host=host, port=port, timeout=5)

            # self._client.connect()
        except Exception as err:
            # always try to stop the bridge, as it will keep retrying
            # in the background otherwise!
            if self._client is not None:
                self._client.close()

            raise err

    async def _async_update_data(self):
        try:
            if not self._client.connected:
                await self._client.connect()
            else:
                # check alive
                try:
                    await self._client.read_holding_registers(
                        address=0x0, count=1, device_id=self._unit_id
                    )
                except ModbusIOException as merr:
                    # merr.isError()
                    await self._client.connect()

            async with asyncio.timeout(30):
                return await self.device.update(self._client, self._unit_id)
        except Exception as err:
            raise UpdateFailed(f"Could not update values: {err}") from err

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this pm device."""
        # _LOGGER.debug(self.coordinator.config_entry.data)
        match self._entry.data[CONF_METER_TYPE]:
            case MeterTypes.METER_TYPE_CT_3P:
                meter_type_name = "DTSU-666"
            case _:
                meter_type_name = "DTSU-666-H"
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Chint",
            model=meter_type_name,
        )

    async def stop(self):
        """Close the modbus connection"""
        await self._client.close()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        update_coordinators = hass.data[DOMAIN][entry.entry_id][
            DATA_UPDATE_COORDINATORS
        ]
        for update_coordinator in update_coordinators:
            await update_coordinator.stop()

        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_setup(hass: HomeAssistant, config):
    """Set up the chint modbus component."""
    hass.data[DOMAIN] = {}
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up a chint mobus."""
    device = ChintDxsuDevice(
        hass,
        entry,
        UPDATE_INTERVAL,
    )

    update_coordinators = []

    update_coordinators.append(
        await _create_update_coordinator(hass, device, entry, UPDATE_INTERVAL)
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        DATA_UPDATE_COORDINATORS: update_coordinators,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # await async_setup_services(hass, entry, device)
    return True


async def _create_update_coordinator(
    hass: HomeAssistant,
    device: ChintDxsuDevice,
    entry: ConfigEntry,
    update_interval,
):
    coordinator = ChintUpdateCoordinator(
        hass,
        _LOGGER,
        device=device,
        entry=entry,
        update_interval=update_interval,
    )

    await coordinator.create_client(entry.data[CONF_PORT], entry.data[CONF_HOST])

    await coordinator.async_config_entry_first_refresh()

    return coordinator


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug("Migrating from version %s", config_entry.version)

    if config_entry.version < 2:
        data = {**config_entry.data}

        data[CONF_METER_TYPE] = MeterTypes.METER_TYPE_H_3P

        config_entry.version = 2
        hass.config_entries.async_update_entry(config_entry, data=data)

    _LOGGER.info("Migration to version %s successful", config_entry.version)

    return True
