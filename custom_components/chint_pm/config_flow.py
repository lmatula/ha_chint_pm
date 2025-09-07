"""Config flow for Chint pm integration."""

from __future__ import annotations

import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import serial.tools.list_ports
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import usb
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_TYPE,
    CONF_USERNAME,
)
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_PHASE_MODE,
    CONF_SLAVE_IDS,
    CONF_METER_TYPE,
    DEFAULT_PORT,
    DEFAULT_SERIAL_SLAVE_ID,
    DEFAULT_SLAVE_ID,
    DEFAULT_USERNAME,
    DOMAIN,
    PHMODE_3P4W,
    PHMODE_3P3W,
    MeterTypes,
)

from pymodbus.client import ModbusSerialClient, ModbusTcpClient

_LOGGER = logging.getLogger(__name__)

STEP_SETUP_NETWORK_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Required(CONF_SLAVE_IDS, default=str(DEFAULT_SLAVE_ID)): str,
    }
)

STEP_LOGIN_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

STEP_PM_CONFIG_DATA_SCHEMA = vol.Schema(
    {vol.Required(CONF_PHASE_MODE): vol.In(["3P4W", "3P3W"])}
)

STEP_METER_TYPE_CONFIG_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_METER_TYPE): vol.In(
            {
                MeterTypes.METER_TYPE_H_3P: "DTSU666-H (Huawei)",
                MeterTypes.METER_TYPE_CT_3P: "DTSU666 (Normal)",
            }
        )
    }
)

CONF_MANUAL_PATH = "Enter Manually"


def _resolve_ph_mode(net: int) -> str:
    if net == 0:
        return PHMODE_3P4W
    else:
        return PHMODE_3P3W


async def validate_serial_setup(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the serial device that was passed by the user."""

    client = None
    try:
        client = ModbusSerialClient(
            port=data[CONF_PORT], baudrate=9600, bytesize=8, stopbits=1, parity="N"
        )
        client.connect()

        rr = client.read_holding_registers(
            address=0x0, count=4, device_id=data[CONF_SLAVE_IDS][0]
        )
        decoder = client.convert_from_registers(
            rr.registers, data_type=client.DATATYPE.UINT16
        )
        rev = decoder[0]
        ucode = decoder[1]
        clre = decoder[2]
        net = decoder[3]

        rr = client.read_holding_registers(
            address=0xB, count=1, device_id=data[CONF_SLAVE_IDS][0]
        )
        decoder = client.convert_from_registers(
            rr.registers, data_type=client.DATATYPE.UINT16
        )
        # device_type = decoder[0]

        _LOGGER.info(
            "Successfully connected to pm phase mode %s",
            net,
        )

        match data[CONF_METER_TYPE]:
            case MeterTypes.METER_TYPE_CT_3P:
                meter_type_name = "DTSU-666"
            case _:
                meter_type_name = "DTSU-666-H"

        result = {
            "model_name": f"{meter_type_name} ({data[CONF_PORT]}@{data[CONF_SLAVE_IDS][0]})",
            "rev": rev,
            CONF_PHASE_MODE: _resolve_ph_mode(net),
        }

        # Return info that you want to store in the config entry.
        return result

    finally:
        if client is not None:
            # Cleanup this inverter object explicitly to prevent it from trying to maintain a modbus connection
            client.close()


async def validate_network_setup(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.
    Data has the keys from STEP_SETUP_NETWORK_DATA_SCHEMA with values provided by the user.
    """

    client = None
    try:
        client = ModbusTcpClient(host=data[CONF_HOST], port=data[CONF_PORT], timeout=5)
        client.connect()

        rr = client.read_holding_registers(
            address=0x0, count=4, device_id=data[CONF_SLAVE_IDS][0]
        )
        decoder = client.convert_from_registers(
            rr.registers, data_type=client.DATATYPE.UINT16
        )
        rev = decoder[0]
        ucode = decoder[1]
        clre = decoder[2]
        net = decoder[3]

        rr = client.read_holding_registers(
            address=0xB, count=1, device_id=data[CONF_SLAVE_IDS][0]
        )
        decoder = client.convert_from_registers(
            rr.registers, data_type=client.DATATYPE.UINT16
        )
        # device_type = decoder[0]

        _LOGGER.info(
            "Successfully connected to pm phase mode %s",
            net,
        )

        match data[CONF_METER_TYPE]:
            case MeterTypes.METER_TYPE_CT_3P:
                meter_type_name = "DTSU-666"
            case _:
                meter_type_name = "DTSU-666-H"

        result = {
            "model_name": f"{meter_type_name} ({data[CONF_HOST]}:{data[CONF_PORT]}@{data[CONF_SLAVE_IDS][0]})",
            "rev": rev,
            CONF_PHASE_MODE: _resolve_ph_mode(net),
        }

        # Return info that you want to store in the config entry.
        return result

    finally:
        if client is not None:
            # Cleanup this inverter object explicitly to prevent it from trying to maintain a modbus connection
            client.close()


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for chint pm."""

    VERSION = 3

    def __init__(self) -> None:
        """Initialize flow."""

        self._host: str | None = None
        self._port: str | None = None
        self._slave_ids: list[int] | None = None
        self._info: dict | None = None
        self._username: str | None = None
        self._password: str | None = None
        self._pm_phase_mode: str | None = None
        self._meter_type: str | None = None

        # Only used in reauth flows:
        self._reauth_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step when user initializes a integration."""
        return await self.async_step_setup_meter_type()

    async def async_step_connection_type(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step when user initializes a integration."""
        if user_input is not None:
            user_selection = user_input[CONF_TYPE]
            if user_selection == "Serial":
                return await self.async_step_setup_serial()

            return await self.async_step_setup_network()

        list_of_types = ["Serial", "Network"]

        schema = vol.Schema({vol.Required(CONF_TYPE): vol.In(list_of_types)})
        return self.async_show_form(step_id="connection_type", data_schema=schema)

    async def async_step_setup_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handles connection parameters when using ModbusRTU."""

        # Parameter configuration is always possible over serial connection

        errors = {}

        if user_input is not None:
            user_selection = user_input[CONF_PORT]
            if user_selection == CONF_MANUAL_PATH:
                self._slave_ids = user_input[CONF_SLAVE_IDS]
                return await self.async_step_setup_serial_manual_path()

            user_input[CONF_PORT] = await self.hass.async_add_executor_job(
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
                    info = await validate_serial_setup(
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

        list_of_ports[CONF_MANUAL_PATH] = CONF_MANUAL_PATH

        schema = vol.Schema(
            {
                vol.Required(CONF_PORT): vol.In(list_of_ports),
                vol.Required(CONF_SLAVE_IDS, default=str(DEFAULT_SERIAL_SLAVE_ID)): str,
            }
        )
        return self.async_show_form(
            step_id="setup_serial",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_setup_serial_manual_path(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select path manually."""
        errors = {}

        if user_input is not None:
            try:
                user_input[CONF_SLAVE_IDS] = list(
                    map(int, user_input[CONF_SLAVE_IDS].split(","))
                )
            except ValueError:
                errors["base"] = "invalid_slave_ids"
            else:
                try:
                    info = await validate_serial_setup(
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

        schema = vol.Schema(
            {
                vol.Required(CONF_PORT): str,
                vol.Required(CONF_SLAVE_IDS, default=self._slave_ids): str,
            }
        )
        return self.async_show_form(
            step_id="setup_serial_manual_path", data_schema=schema, errors=errors
        )

    async def async_step_setup_network(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handles connection parameters when using ModbusTCP."""

        errors = {}

        if user_input is not None:
            try:
                user_input[CONF_SLAVE_IDS] = list(
                    map(int, user_input[CONF_SLAVE_IDS].split(","))
                )
            except ValueError:
                errors["base"] = "invalid_slave_ids"
            else:
                try:
                    info = await validate_network_setup(
                        {
                            CONF_HOST: user_input[CONF_HOST],
                            CONF_PORT: user_input[CONF_PORT],
                            CONF_SLAVE_IDS: user_input[CONF_SLAVE_IDS],
                            CONF_METER_TYPE: self._meter_type,
                        }
                    )

                except SlaveException:
                    errors["base"] = "slave_cannot_connect"

                    errors["base"] = "read_error"
                except Exception as exception:  # pylint: disable=broad-except
                    _LOGGER.exception(exception)
                    errors["base"] = "unknown"
                else:
                    await self.async_set_unique_id()
                    self._abort_if_unique_id_configured()

                    self._host = user_input[CONF_HOST]
                    self._port = user_input[CONF_PORT]
                    self._slave_ids = user_input[CONF_SLAVE_IDS]

                    self._info = info

                    self.context["title_placeholders"] = {"name": info["model_name"]}

                    # Otherwise, we can directly create the device entry!
                    return await self.async_step_pm_settings()
                    # return await self._create_entry()

        return self.async_show_form(
            step_id="setup_network",
            data_schema=STEP_SETUP_NETWORK_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_setup_meter_type(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """enter pm configs"""
        errors = {}
        if user_input is not None:
            try:
                self._meter_type = user_input[CONF_METER_TYPE]
                return await self.async_step_connection_type()

            except Exception as exception:  # pylint: disable=broad-except
                _LOGGER.exception(exception)
                errors["base"] = "unknown"
        return self.async_show_form(
            step_id="setup_meter_type",
            data_schema=STEP_METER_TYPE_CONFIG_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_pm_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """enter pm configs"""
        errors = {}
        if user_input is not None:
            try:
                self._pm_phase_mode = user_input[CONF_PHASE_MODE]
                return await self._create_entry()

            except Exception as exception:  # pylint: disable=broad-except
                _LOGGER.exception(exception)
                errors["base"] = "unknown"
        return self.async_show_form(
            step_id="pm_settings", data_schema=STEP_PM_CONFIG_DATA_SCHEMA, errors=errors
        )

    async def _create_entry(self):
        """Create the entry."""
        assert self._port is not None
        assert self._slave_ids is not None

        data = {
            CONF_HOST: self._host,
            CONF_PORT: self._port,
            CONF_SLAVE_IDS: self._slave_ids,
            CONF_USERNAME: self._username,
            CONF_PASSWORD: self._password,
            CONF_PHASE_MODE: self._pm_phase_mode,
            CONF_METER_TYPE: self._meter_type,
        }

        if self._reauth_entry:
            self.hass.config_entries.async_update_entry(self._reauth_entry, data=data)
            await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        return self.async_create_entry(title=self._info["model_name"], data=data)


class SlaveException(Exception):
    """Error while testing communication with a slave."""
