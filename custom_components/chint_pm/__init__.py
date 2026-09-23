"""The Chint power meter integration."""

from __future__ import annotations

import logging

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_METER_TYPE,
    CONF_PHASE_MODE,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    PHMODE_3P4W,
    MeterTypes,
)
from .coordinator import ChintConfigEntry, ChintUpdateCoordinator, build_unique_id

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ChintConfigEntry) -> bool:
    """Set up a Chint power meter from a config entry."""
    coordinator = ChintUpdateCoordinator(hass, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        # The client is created during the first refresh, so it has to be closed
        # here as well - async_on_unload does not run for a failed setup.
        await coordinator.async_close()
        raise

    entry.runtime_data = coordinator
    entry.async_on_unload(coordinator.async_close)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ChintConfigEntry) -> None:
    """Reload the entry when its options change, e.g. the update interval."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ChintConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: ChintConfigEntry) -> bool:
    """Migrate an old config entry."""
    _LOGGER.debug("Migrating configuration from version %s", entry.version)

    if entry.version > CONFIG_ENTRY_VERSION:
        # Downgrading from a future version is not supported.
        return False

    data = {**entry.data}

    if entry.version < CONFIG_ENTRY_VERSION:
        # The meter type arrived with version 2; anything older could only ever
        # talk to the -H variant.
        data.setdefault(CONF_METER_TYPE, MeterTypes.METER_TYPE_H_3P.value)
        data.setdefault(CONF_PHASE_MODE, PHMODE_3P4W)
        # Never used - the meter has no authentication.
        data.pop(CONF_USERNAME, None)
        data.pop(CONF_PASSWORD, None)

    # Entries created by earlier versions have no unique id at all, which left
    # them without any protection against being added twice. Only claim one if
    # it is still free, so a duplicated setup does not break the migration.
    unique_id = entry.unique_id
    if unique_id is None:
        candidate = build_unique_id(data)
        if not hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, candidate):
            unique_id = candidate

    hass.config_entries.async_update_entry(
        entry, data=data, unique_id=unique_id, version=CONFIG_ENTRY_VERSION
    )
    _LOGGER.debug("Migration to version %s successful", entry.version)
    return True
