"""Config flow for the Chint power meter integration."""

from __future__ import annotations

import logging
from typing import Any

from pymodbus.client import AsyncModbusSerialClient, AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException
import serial.tools.list_ports
import voluptuous as vol

from homeassistant.components import usb
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL, CONF_TYPE
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_METER_TYPE,
    CONF_PHASE_MODE,
    CONF_SECOND_CHANNEL,
    CONF_SLAVE_IDS,
    CONFIG_ENTRY_VERSION,
    CONNECTION_NETWORK,
    CONNECTION_SERIAL,
    DEFAULT_PORT,
    DEFAULT_SERIAL_SLAVE_ID,
    DEFAULT_SLAVE_ID,
    DEFAULT_SLAVE_ID_20,
    METER_TYPES_ADDRESS_1,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
    MODBUS_BAUDRATE,
    MODBUS_TIMEOUT,
    PHMODE_3P3W,
    PHMODE_3P4W,
    MeterTypes,
)
from .coordinator import build_unique_id, meter_model

_LOGGER = logging.getLogger(__name__)

CONF_MANUAL_PATH = "manual_path"

STEP_METER_TYPE_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_METER_TYPE): SelectSelector(
            SelectSelectorConfig(
                options=[
                    MeterTypes.METER_TYPE_H_3P.value,
                    MeterTypes.METER_TYPE_CT_3P.value,
                    MeterTypes.METER_TYPE_20_3P.value,
                    MeterTypes.METER_TYPE_20_SUNGROW_3P.value,
                ],
                translation_key="meter_type",
                mode=SelectSelectorMode.LIST,
            )
        )
    }
)

STEP_CONNECTION_TYPE_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TYPE): SelectSelector(
            SelectSelectorConfig(
                options=[CONNECTION_SERIAL, CONNECTION_NETWORK],
                translation_key="connection_type",
                mode=SelectSelectorMode.LIST,
            )
        )
    }
)


def _default_slave_id(meter_type: str | None) -> int:
    """Return the Modbus address the meter type ships with."""
    if meter_type in METER_TYPES_ADDRESS_1:
        return DEFAULT_SLAVE_ID_20
    return DEFAULT_SLAVE_ID


def _network_schema(meter_type: str | None) -> vol.Schema:
    """Build the Modbus TCP form, pre-filled with the type's default address."""
    return vol.Schema(
        {
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
            vol.Required(
                CONF_SLAVE_IDS, default=str(_default_slave_id(meter_type))
            ): str,
        }
    )


class CannotConnect(Exception):
    """The meter could not be reached."""


class ReadError(Exception):
    """The meter answered, but not with usable data."""


def _resolve_phase_mode(net: int) -> str:
    """Translate the meter's wiring register into a phase mode."""
    return PHMODE_3P4W if net == 0 else PHMODE_3P3W


async def _async_validate_setup(data: dict[str, Any]) -> dict[str, Any]:
    """Connect to the meter and read back enough to confirm it is there.

    Uses the async pymodbus clients so nothing blocks the event loop.
    """
    unit_id = data[CONF_SLAVE_IDS][0]
    client: AsyncModbusSerialClient | AsyncModbusTcpClient
    if host := data.get(CONF_HOST):
        client = AsyncModbusTcpClient(
            host=host, port=data[CONF_PORT], timeout=MODBUS_TIMEOUT
        )
        location = f"{host}:{data[CONF_PORT]}@{unit_id}"
    else:
        client = AsyncModbusSerialClient(
            port=data[CONF_PORT],
            baudrate=MODBUS_BAUDRATE,
            bytesize=8,
            stopbits=1,
            parity="N",
            timeout=MODBUS_TIMEOUT,
        )
        location = f"{data[CONF_PORT]}@{unit_id}"

    try:
        if not await client.connect():
            raise CannotConnect(f"Could not connect to {location}")

        if data[CONF_METER_TYPE] == MeterTypes.METER_TYPE_20_SUNGROW_3P:
            # The Sungrow register map documents no configuration registers,
            # so check that the measurement block answers and assume 3P4W.
            result = await client.read_holding_registers(
                address=0x1100, count=2, device_id=unit_id
            )
            if result.isError():
                raise ReadError(f"{location} rejected the identification read")
            revision, net = None, 0
        else:
            # Firmware revision (0x0000) and wiring mode (0x0003), read one by
            # one: the DTSU666-20 manual does not document 0x0002, so a block
            # read spanning it may be rejected.
            identification = []
            for address in (0x0000, 0x0003):
                result = await client.read_holding_registers(
                    address=address, count=1, device_id=unit_id
                )
                if result.isError():
                    raise ReadError(f"{location} rejected the identification read")
                identification.append(result.registers[0])
            revision, net = identification

        channels = 1
        if data[CONF_METER_TYPE] == MeterTypes.METER_TYPE_20_3P:
            channels = await _async_read_channel_count(client, unit_id)
    except ModbusException as err:
        raise CannotConnect(f"Modbus error while talking to {location}: {err}") from err
    finally:
        # Do not keep a connection around; the coordinator opens its own.
        client.close()

    _LOGGER.debug("Connected to meter at %s, wiring register: %s", location, net)

    return {
        "model_name": f"{meter_model(data[CONF_METER_TYPE])} ({location})",
        "rev": revision,
        "channels": channels,
        CONF_PHASE_MODE: _resolve_phase_mode(net),
    }


async def _async_read_channel_count(
    client: AsyncModbusSerialClient | AsyncModbusTcpClient, unit_id: int
) -> int:
    """Read how many current channels a DTSU666-20 has.

    The device identification code at 0x002B is 0x03CS: C is the number of
    channels, S the CT size (7 = 100 A, 8 = 250 A). Falls back to one channel
    if the meter does not answer or reports something unexpected.
    """
    result = await client.read_holding_registers(
        address=0x002B, count=1, device_id=unit_id
    )
    if result.isError():
        _LOGGER.debug("Meter did not report its device identification code")
        return 1
    device_id = result.registers[0]
    _LOGGER.debug("Device identification code 0x%04X", device_id)
    channels = (device_id >> 4) & 0xF
    return channels if channels in (1, 2) else 1


def _parse_slave_ids(raw: str) -> list[int]:
    """Parse the comma separated Modbus unit id field."""
    return [int(part) for part in raw.split(",")]


class ChintConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Chint power meter."""

    VERSION = CONFIG_ENTRY_VERSION

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ChintOptionsFlow:
        """Get the options flow for this handler."""
        return ChintOptionsFlow()

    def __init__(self) -> None:
        """Initialise the flow."""
        self._meter_type: str | None = None
        self._data: dict[str, Any] = {}
        self._info: dict[str, Any] = {}
        self._slave_ids_raw: str = str(DEFAULT_SERIAL_SLAVE_ID)
        self._options: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which meter variant is being set up."""
        if user_input is not None:
            self._meter_type = user_input[CONF_METER_TYPE]
            self._slave_ids_raw = str(_default_slave_id(self._meter_type))
            return await self.async_step_connection_type()

        return self.async_show_form(
            step_id="user", data_schema=STEP_METER_TYPE_DATA_SCHEMA
        )

    async def async_step_connection_type(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask whether the meter is reached over serial or over the network."""
        if user_input is not None:
            if user_input[CONF_TYPE] == CONNECTION_SERIAL:
                return await self.async_step_setup_serial()
            return await self.async_step_setup_network()

        return self.async_show_form(
            step_id="connection_type", data_schema=STEP_CONNECTION_TYPE_DATA_SCHEMA
        )

    async def async_step_setup_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle connection parameters for Modbus RTU."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._slave_ids_raw = user_input[CONF_SLAVE_IDS]
            if user_input[CONF_PORT] == CONF_MANUAL_PATH:
                return await self.async_step_setup_serial_manual_path()

            device_path = await self.hass.async_add_executor_job(
                usb.get_serial_by_id, user_input[CONF_PORT]
            )
            result = await self._async_try_create_entry(
                {CONF_PORT: device_path, CONF_SLAVE_IDS: user_input[CONF_SLAVE_IDS]},
                errors,
            )
            if result is not None:
                return result

        ports = await self.hass.async_add_executor_job(serial.tools.list_ports.comports)
        list_of_ports = {
            port.device: usb.human_readable_device_name(
                port.device,
                port.serial_number,
                port.manufacturer,
                port.description,
                port.vid,
                port.pid,
            )
            for port in ports
        }
        list_of_ports[CONF_MANUAL_PATH] = "Enter manually"

        return self.async_show_form(
            step_id="setup_serial",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PORT): vol.In(list_of_ports),
                    vol.Required(CONF_SLAVE_IDS, default=self._slave_ids_raw): str,
                }
            ),
            errors=errors,
        )

    async def async_step_setup_serial_manual_path(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user type the serial device path."""
        errors: dict[str, str] = {}

        if user_input is not None:
            result = await self._async_try_create_entry(
                {
                    CONF_PORT: user_input[CONF_PORT],
                    CONF_SLAVE_IDS: user_input[CONF_SLAVE_IDS],
                },
                errors,
            )
            if result is not None:
                return result

        return self.async_show_form(
            step_id="setup_serial_manual_path",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PORT): str,
                    vol.Required(CONF_SLAVE_IDS, default=self._slave_ids_raw): str,
                }
            ),
            errors=errors,
        )

    async def async_step_setup_network(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle connection parameters for Modbus TCP."""
        errors: dict[str, str] = {}

        if user_input is not None:
            result = await self._async_try_create_entry(
                {
                    CONF_HOST: user_input[CONF_HOST],
                    CONF_PORT: user_input[CONF_PORT],
                    CONF_SLAVE_IDS: user_input[CONF_SLAVE_IDS],
                },
                errors,
            )
            if result is not None:
                return result

        return self.async_show_form(
            step_id="setup_network",
            data_schema=_network_schema(self._meter_type),
            errors=errors,
        )

    async def async_step_pm_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the wiring mode, pre-filled with what the meter reports."""
        if user_input is not None:
            self._data[CONF_PHASE_MODE] = user_input[CONF_PHASE_MODE]
            if CONF_SECOND_CHANNEL in user_input:
                self._options[CONF_SECOND_CHANNEL] = user_input[CONF_SECOND_CHANNEL]
            return self.async_create_entry(
                title=self._info["model_name"], data=self._data, options=self._options
            )

        schema: dict[Any, Any] = {
            vol.Required(
                CONF_PHASE_MODE,
                default=self._info.get(CONF_PHASE_MODE, PHMODE_3P4W),
            ): vol.In([PHMODE_3P4W, PHMODE_3P3W])
        }
        if self._meter_type == MeterTypes.METER_TYPE_20_3P:
            # Pre-filled with what the device identification code reports.
            schema[
                vol.Required(
                    CONF_SECOND_CHANNEL, default=self._info.get("channels", 1) == 2
                )
            ] = BooleanSelector()

        return self.async_show_form(
            step_id="pm_settings", data_schema=vol.Schema(schema)
        )

    async def _async_try_create_entry(
        self, connection: dict[str, Any], errors: dict[str, str]
    ) -> ConfigFlowResult | None:
        """Validate the connection and move on, or fill ``errors`` and stay put.

        Returns ``None`` when the form has to be shown again.
        """
        try:
            connection[CONF_SLAVE_IDS] = _parse_slave_ids(connection[CONF_SLAVE_IDS])
        except ValueError:
            errors["base"] = "invalid_slave_ids"
            return None

        data = {CONF_METER_TYPE: self._meter_type, **connection}

        await self.async_set_unique_id(build_unique_id(data))
        self._abort_if_unique_id_configured()

        try:
            info = await _async_validate_setup(data)
        except CannotConnect as err:
            _LOGGER.debug("Cannot connect: %s", err)
            errors["base"] = "cannot_connect"
            return None
        except ReadError as err:
            _LOGGER.debug("Read error: %s", err)
            errors["base"] = "read_error"
            return None
        except Exception:
            _LOGGER.exception("Unexpected error while setting up the meter")
            errors["base"] = "unknown"
            return None

        self._data = data
        self._info = info
        self.context["title_placeholders"] = {"name": info["model_name"]}
        return await self.async_step_pm_settings()


class ChintOptionsFlow(OptionsFlow):
    """Handle options for the Chint power meter.

    The update interval, and on the DTSU666-20 whether to read the second
    current channel.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        schema: dict[Any, Any] = {
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=options.get(CONF_SCAN_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_UPDATE_INTERVAL,
                    max=MAX_UPDATE_INTERVAL,
                    step=1,
                    unit_of_measurement="s",
                    mode=NumberSelectorMode.BOX,
                )
            )
        }
        if self.config_entry.data[CONF_METER_TYPE] == MeterTypes.METER_TYPE_20_3P:
            schema[
                vol.Required(
                    CONF_SECOND_CHANNEL,
                    default=options.get(CONF_SECOND_CHANNEL, False),
                )
            ] = BooleanSelector()

        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
