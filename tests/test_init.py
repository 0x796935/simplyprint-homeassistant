"""Test setup and unload of the SimplyPrint integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.simplyprint.const import DOMAIN
from custom_components.simplyprint.entity import account_device_id, printer_device_id

from .conftest import mock_api


async def test_setup_and_unload(
    hass: HomeAssistant, aioclient_mock, mock_config_entry
) -> None:
    """The entry sets up, creates devices, and unloads cleanly."""
    mock_config_entry.add_to_hass(hass)
    mock_api(aioclient_mock)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.LOADED

    dev_reg = dr.async_get(hass)
    # Account device + one device per printer.
    assert dev_reg.async_get_device(identifiers={account_device_id("76283")})
    assert dev_reg.async_get_device(identifiers={printer_device_id(50051)})
    assert dev_reg.async_get_device(identifiers={printer_device_id(51887)})

    # Services registered.
    for svc in ("pause", "resume", "cancel", "clear_bed", "send_gcode"):
        assert hass.services.has_service(DOMAIN, svc)

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
    # Services removed once the last entry is gone.
    assert not hass.services.has_service(DOMAIN, "pause")


async def test_setup_auth_failure_triggers_reauth(
    hass: HomeAssistant, aioclient_mock, mock_config_entry
) -> None:
    """A 403 during the first refresh puts the entry into setup-retry/reauth."""
    mock_config_entry.add_to_hass(hass)
    aioclient_mock.post(
        "https://api.simplyprint.io/76283/printers/Get", status=403
    )

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
