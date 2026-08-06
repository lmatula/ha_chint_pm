"""Config flow for the Chint power meter integration."""

from __future__ import annotations

import logging
from typing import Any

from pymodbus.client import AsyncModbusSerialClient, AsyncModbusTcpClient
from pymodbus.client.mixin import ModbusClientMixin
from pymodbus.exceptions import ModbusException
import serial.tools.list_ports
import voluptuous as vol
import asyncio

from homeassistant.components import usb
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TYPE
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_METER_TYPE,
    CONF_PHASE_MODE,
    CONF_SLAVE_IDS,
    CONFIG_ENTRY_VERSION,
    CONNECTION_NETWORK,
    CONNECTION_SERIAL,
    DEFAULT_PORT,
    DEFAULT_SERIAL_SLAVE_ID,
    DEFAULT_SLAVE_ID,
    DOMAIN,
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

STEP_SETUP_NETWORK_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Required(CONF_SLAVE_IDS, default=str(DEFAULT_SLAVE_ID)): str,
    }
)


class CannotConnect(Exception):
    """The meter could not be reached."""


class ReadError(Exception):
    """The meter answered, but not with usable data."""

def validate_serial_setup(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the serial device that was passed by the user."""

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

        result = await client.read_holding_registers(
            address=0x0, count=4, device_id=unit_id
        )
        if result.isError():
            raise ReadError(f"{location} rejected the identification read")

        decoded = client.convert_from_registers(
            result.registers, data_type=ModbusClientMixin.DATATYPE.UINT16
        )
        revision, net = decoded[0], decoded[3]
    except ModbusException as err:
        raise CannotConnect(f"Modbus error while talking to {location}: {err}") from err
    finally:
        # Do not keep a connection around; the coordinator opens its own.
        client.close()

    _LOGGER.debug("Connected to meter at %s, wiring register: %s", location, net)

    return {
        "model_name": f"{meter_model(data[CONF_METER_TYPE])} ({location})",
        "rev": revision,
        CONF_PHASE_MODE: _resolve_phase_mode(net),
    }


def _parse_slave_ids(raw: str) -> list[int]:
    """Parse the comma separated Modbus unit id field."""
    return [int(part) for part in raw.split(",")]


class ChintConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Chint power meter."""

    VERSION = CONFIG_ENTRY_VERSION

    def __init__(self) -> None:
        """Initialise the flow."""
        self._meter_type: str | None = None
        self._data: dict[str, Any] = {}
        self._info: dict[str, Any] = {}
        self._slave_ids_raw: str = str(DEFAULT_SERIAL_SLAVE_ID)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which meter variant is being set up."""
        if user_input is not None:
            self._meter_type = user_input[CONF_METER_TYPE]
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

            try:
                user_input[CONF_SLAVE_IDS] = list(
                    map(int, user_input[CONF_SLAVE_IDS].split(","))
                )
            except ValueError:
                errors["base"] = "invalid_slave_ids"
            else:
                try:
                    loop = asyncio.get_running_loop()
                    info = await loop.run_in_executor(None, validate_serial_setup,
                        {
                            CONF_PORT: user_input[CONF_PORT],
                            CONF_SLAVE_IDS: user_input[CONF_SLAVE_IDS],
                            CONF_METER_TYPE: self._meter_type,
                        }
                    )

                except SlaveException:
                    errors["base"] = "slave_cannot_connect"
                except Exception as exception:  # pylint: disable=broad-except
                    _LOGGER.exception(exception)
                    errors["base"] = "unknown"
                else:
                    await self.async_set_unique_id()
                    self._abort_if_unique_id_configured(
                        updates={
                            CONF_HOST: None,
                            CONF_PORT: user_input[CONF_PORT],
                            CONF_SLAVE_IDS: user_input[CONF_SLAVE_IDS],
                        }
                    )

                    self._port = user_input[CONF_PORT]
                    self._slave_ids = user_input[CONF_SLAVE_IDS]

                    self._info = info

                    self.context["title_placeholders"] = {"name": info["model_name"]}

                    # We can directly make the new entry
                    return await self.async_step_pm_settings()
                    # return await self._create_entry()

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
                    vol.Required(
                        CONF_SLAVE_IDS, default=str(DEFAULT_SERIAL_SLAVE_ID)
                    ): str,
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
            data_schema=STEP_SETUP_NETWORK_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_pm_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the wiring mode, pre-filled with what the meter reports."""
        if user_input is not None:
            self._data[CONF_PHASE_MODE] = user_input[CONF_PHASE_MODE]
            return self.async_create_entry(
                title=self._info["model_name"], data=self._data
            )

        return self.async_show_form(
            step_id="pm_settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PHASE_MODE,
                        default=self._info.get(CONF_PHASE_MODE, PHMODE_3P4W),
                    ): vol.In([PHMODE_3P4W, PHMODE_3P3W])
                }
            ),
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
