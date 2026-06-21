"""Test SimplyPrint entities, buttons and services."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.simplyprint.const import DOMAIN

from .conftest import mock_api


def _eid(hass: HomeAssistant, platform: str, unique_suffix: str) -> str:
    ent_reg = er.async_get(hass)
    eid = ent_reg.async_get_entity_id(
        platform, DOMAIN, f"{DOMAIN}_{unique_suffix}"
    )
    assert eid, f"entity {unique_suffix} not found"
    return eid


async def _setup(hass, aioclient_mock, mock_config_entry, **kw):
    mock_config_entry.add_to_hass(hass)
    mock_api(aioclient_mock, **kw)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()


async def test_printer_sensors(
    hass: HomeAssistant, aioclient_mock, mock_config_entry
) -> None:
    """Printer sensors reflect the polled data."""
    await _setup(hass, aioclient_mock, mock_config_entry)

    assert hass.states.get(_eid(hass, "sensor", "50051_status")).state == "printing"
    assert hass.states.get(_eid(hass, "sensor", "50051_progress")).state == "42.0"
    assert (
        hass.states.get(_eid(hass, "sensor", "50051_nozzle_temperature")).state
        == "215.0"
    )
    assert (
        hass.states.get(_eid(hass, "sensor", "50051_bed_temperature")).state
        == "60.0"
    )
    assert (
        hass.states.get(_eid(hass, "sensor", "50051_job_name")).state
        == "benchy.gcode"
    )
    # time_remaining: 600 s shown in minutes -> 10.0
    assert (
        hass.states.get(_eid(hass, "sensor", "50051_time_remaining")).state == "10.0"
    )
    assert (
        hass.states.get(_eid(hass, "sensor", "50051_filament_type")).state == "PLA"
    )

    # Idle printer has no job -> progress unknown.
    assert hass.states.get(_eid(hass, "sensor", "51887_progress")).state == "unknown"
    assert (
        hass.states.get(_eid(hass, "sensor", "51887_status")).state == "operational"
    )


async def test_print_render_image(
    hass: HomeAssistant, aioclient_mock, mock_config_entry
) -> None:
    """The printing printer resolves a gcode render + analysis."""
    await _setup(hass, aioclient_mock, mock_config_entry)

    coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]
    render = coordinator.data["printers"][50051].get("render")
    assert render is not None
    assert render["url"] == "https://cdn.simplyprint.io/i/user/file/benchyfileid.png"
    assert render["analysis"]["totalLayers"] == 80

    # Printing printer: image entity available with analysis attributes.
    img = hass.states.get(_eid(hass, "image", "50051_print_render"))
    assert img is not None
    assert img.state != "unavailable"
    assert img.attributes["slicer"] == "OrcaSlicer"
    assert img.attributes["total_layers"] == 80

    # total_layers sensor reflects the analysis.
    assert (
        hass.states.get(_eid(hass, "sensor", "50051_total_layers")).state == "80"
    )

    # Idle printer: no render, image unavailable.
    assert coordinator.data["printers"][51887].get("render") is None
    assert (
        hass.states.get(_eid(hass, "image", "51887_print_render")).state
        == "unavailable"
    )


async def test_binary_sensors(
    hass: HomeAssistant, aioclient_mock, mock_config_entry
) -> None:
    """Binary sensors reflect printer flags."""
    await _setup(hass, aioclient_mock, mock_config_entry)

    assert hass.states.get(_eid(hass, "binary_sensor", "50051_online")).state == "on"
    assert (
        hass.states.get(_eid(hass, "binary_sensor", "50051_printing")).state == "on"
    )
    assert (
        hass.states.get(_eid(hass, "binary_sensor", "51887_printing")).state == "off"
    )


async def test_account_sensors_with_statistics(
    hass: HomeAssistant, aioclient_mock, mock_config_entry
) -> None:
    """Account aggregate and statistics sensors populate correctly."""
    mock_config_entry.add_to_hass(hass)
    # Enable statistics via options before setup.
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={"scan_interval": 30, "enable_statistics": True, "statistics_days": 30},
    )
    mock_api(
        aioclient_mock,
        statistics={
            "total_print_seconds": 7200,
            "total_filament_usage_gram": 123.4,
            "print_job_count": 10,
            "done_print_jobs": 8,
            "failed_print_jobs": 2,
        },
    )
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert (
        hass.states.get(_eid(hass, "sensor", "account_76283_total_printers")).state
        == "2"
    )
    assert (
        hass.states.get(
            _eid(hass, "sensor", "account_76283_printing_printers")
        ).state
        == "1"
    )
    # 7200 s -> 2.0 h
    assert (
        hass.states.get(
            _eid(hass, "sensor", "account_76283_total_print_time")
        ).state
        == "2.0"
    )
    assert (
        hass.states.get(
            _eid(hass, "sensor", "account_76283_done_print_jobs")
        ).state
        == "8"
    )


async def test_button_press_calls_api(
    hass: HomeAssistant, aioclient_mock, mock_config_entry
) -> None:
    """Pressing the pause button hits the Pause endpoint with the right pid."""
    await _setup(hass, aioclient_mock, mock_config_entry)

    before = len(aioclient_mock.mock_calls)
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": _eid(hass, "button", "50051_pause")},
        blocking=True,
    )
    calls = aioclient_mock.mock_calls[before:]
    pause_calls = [c for c in calls if "printers/actions/Pause" in str(c[1])]
    assert pause_calls, "Pause endpoint was not called"
    assert "pid=50051" in str(pause_calls[0][1])


async def test_service_targets_device(
    hass: HomeAssistant, aioclient_mock, mock_config_entry
) -> None:
    """The cancel service resolves a device target to the right printer."""
    await _setup(hass, aioclient_mock, mock_config_entry)

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device(identifiers={(DOMAIN, "printer_50051")})
    assert device

    before = len(aioclient_mock.mock_calls)
    await hass.services.async_call(
        DOMAIN,
        "cancel",
        {"device_id": [device.id], "comment": "test"},
        blocking=True,
    )
    calls = aioclient_mock.mock_calls[before:]
    cancel_calls = [c for c in calls if "printers/actions/Cancel" in str(c[1])]
    assert cancel_calls, "Cancel endpoint was not called"
    assert "pid=50051" in str(cancel_calls[0][1])


async def test_service_no_target_raises(
    hass: HomeAssistant, aioclient_mock, mock_config_entry
) -> None:
    """A target that matches no printer raises a validation error."""
    from homeassistant.exceptions import ServiceValidationError

    await _setup(hass, aioclient_mock, mock_config_entry)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "pause",
            {"device_id": ["does-not-exist"]},
            blocking=True,
        )
