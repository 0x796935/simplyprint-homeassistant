"""The SimplyPrint integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SimplyPrintApiClient
from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_COMPANY_ID,
    DEFAULT_BASE_URL,
    DOMAIN,
    MANUFACTURER,
    PANEL_URL,
)
from .coordinator import SimplyPrintCoordinator
from .entity import account_device_id
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.IMAGE,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SimplyPrint from a config entry."""
    session = async_get_clientsession(hass)
    client = SimplyPrintApiClient(
        session,
        entry.data[CONF_API_KEY],
        entry.data[CONF_COMPANY_ID],
        entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
    )

    coordinator = SimplyPrintCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Register the account device up front so the per-printer devices can
    # reference it as their `via_device` without racing the platform setup
    # order (HA 2025.12 warns when `via_device` points at a missing device).
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={account_device_id(client.company_id)},
        manufacturer=MANUFACTURER,
        name=f"SimplyPrint ({client.company_id})",
        model="Account",
        configuration_url=PANEL_URL,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async_setup_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        domain_data = hass.data.get(DOMAIN)
        if domain_data is not None:
            domain_data.pop(entry.entry_id, None)
            if not domain_data:
                hass.data.pop(DOMAIN, None)
                async_unload_services(hass)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
