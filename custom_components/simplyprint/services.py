"""Service handlers for SimplyPrint printer actions."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.const import ATTR_AREA_ID, ATTR_DEVICE_ID, ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .api import SimplyPrintApiError
from .const import (
    ATTR_COMMENT,
    ATTR_GCODE,
    ATTR_MACRO,
    ATTR_RATING,
    ATTR_REASON,
    ATTR_RETURN_POSITION,
    ATTR_RETURN_TO_QUEUE,
    ATTR_SUCCESS,
    DOMAIN,
    PRINTER_DEVICE_PREFIX,
    SERVICE_CANCEL,
    SERVICE_CLEAR_BED,
    SERVICE_PAUSE,
    SERVICE_RESUME,
    SERVICE_SEND_GCODE,
)
from .coordinator import SimplyPrintCoordinator

_LOGGER = logging.getLogger(__name__)

_TARGET_SCHEMA = {
    vol.Optional(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(ATTR_ENTITY_ID): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(ATTR_AREA_ID): vol.All(cv.ensure_list, [cv.string]),
}

_CANCEL_SCHEMA = vol.Schema(
    {
        **_TARGET_SCHEMA,
        vol.Optional(ATTR_REASON): vol.Coerce(int),
        vol.Optional(ATTR_COMMENT): cv.string,
        vol.Optional(ATTR_RETURN_TO_QUEUE): cv.boolean,
        vol.Optional(ATTR_RETURN_POSITION): vol.In(
            ["original", "bottom", "top"]
        ),
    }
)

_CLEAR_BED_SCHEMA = vol.Schema(
    {
        **_TARGET_SCHEMA,
        vol.Optional(ATTR_SUCCESS): cv.boolean,
        vol.Optional(ATTR_RATING): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=4)
        ),
    }
)

_SEND_GCODE_SCHEMA = vol.Schema(
    {
        **_TARGET_SCHEMA,
        vol.Optional(ATTR_GCODE): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_MACRO): cv.string,
    }
)

_BASE_SCHEMA = vol.Schema(_TARGET_SCHEMA)


def _resolve_targets(
    hass: HomeAssistant, call: ServiceCall
) -> list[tuple[SimplyPrintCoordinator, int]]:
    """Resolve a service target into ``(coordinator, printer_id)`` pairs."""
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    device_ids: set[str] = set(call.data.get(ATTR_DEVICE_ID, []))

    # Expand entity targets into their owning device.
    for entity_id in call.data.get(ATTR_ENTITY_ID, []):
        entity = ent_reg.async_get(entity_id)
        if entity and entity.device_id:
            device_ids.add(entity.device_id)

    # Expand area targets into devices in that area.
    for area_id in call.data.get(ATTR_AREA_ID, []):
        for device in dr.async_entries_for_area(dev_reg, area_id):
            device_ids.add(device.id)

    store: dict[str, SimplyPrintCoordinator] = hass.data.get(DOMAIN, {})
    targets: list[tuple[SimplyPrintCoordinator, int]] = []
    seen: set[tuple[str, int]] = set()

    for device_id in device_ids:
        device = dev_reg.async_get(device_id)
        if not device:
            continue
        pid: int | None = None
        for domain, ident in device.identifiers:
            if domain == DOMAIN and ident.startswith(f"{PRINTER_DEVICE_PREFIX}_"):
                try:
                    pid = int(ident.split("_", 1)[1])
                except (ValueError, IndexError):
                    pid = None
                break
        if pid is None:
            continue
        for entry_id in device.config_entries:
            coordinator = store.get(entry_id)
            if coordinator and pid in coordinator.printer_ids:
                key = (entry_id, pid)
                if key not in seen:
                    seen.add(key)
                    targets.append((coordinator, pid))
                break

    if not targets:
        raise ServiceValidationError(
            "No SimplyPrint printers matched the service target"
        )
    return targets


def async_setup_services(hass: HomeAssistant) -> None:
    """Register SimplyPrint services (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_PAUSE):
        return

    async def _run(
        call: ServiceCall,
        action: str,
        **extra: Any,
    ) -> None:
        targets = _resolve_targets(hass, call)
        refresh: set[SimplyPrintCoordinator] = set()
        errors: list[str] = []
        for coordinator, pid in targets:
            client = coordinator.client
            try:
                if action == SERVICE_PAUSE:
                    await client.async_pause(pid)
                elif action == SERVICE_RESUME:
                    await client.async_resume(pid)
                elif action == SERVICE_CANCEL:
                    await client.async_cancel(pid, **extra)
                elif action == SERVICE_CLEAR_BED:
                    await client.async_clear_bed(pid, **extra)
                elif action == SERVICE_SEND_GCODE:
                    await client.async_send_gcode(pid, **extra)
            except SimplyPrintApiError as err:
                errors.append(f"printer {pid}: {err}")
                continue
            refresh.add(coordinator)

        for coordinator in refresh:
            await coordinator.async_request_refresh()

        if errors:
            raise HomeAssistantError(
                "SimplyPrint action failed for " + "; ".join(errors)
            )

    async def _pause(call: ServiceCall) -> None:
        await _run(call, SERVICE_PAUSE)

    async def _resume(call: ServiceCall) -> None:
        await _run(call, SERVICE_RESUME)

    async def _cancel(call: ServiceCall) -> None:
        extra = {
            k: call.data[k]
            for k in (
                ATTR_REASON,
                ATTR_COMMENT,
                ATTR_RETURN_TO_QUEUE,
                ATTR_RETURN_POSITION,
            )
            if k in call.data
        }
        await _run(call, SERVICE_CANCEL, **extra)

    async def _clear_bed(call: ServiceCall) -> None:
        extra = {
            k: call.data[k]
            for k in (ATTR_SUCCESS, ATTR_RATING)
            if k in call.data
        }
        await _run(call, SERVICE_CLEAR_BED, **extra)

    async def _send_gcode(call: ServiceCall) -> None:
        gcode = call.data.get(ATTR_GCODE)
        macro = call.data.get(ATTR_MACRO)
        if not gcode and not macro:
            raise ServiceValidationError(
                "Provide either 'gcode' or 'macro' for send_gcode"
            )
        extra: dict[str, Any] = {}
        if gcode:
            extra[ATTR_GCODE] = gcode
        if macro:
            extra[ATTR_MACRO] = macro
        await _run(call, SERVICE_SEND_GCODE, **extra)

    hass.services.async_register(DOMAIN, SERVICE_PAUSE, _pause, schema=_BASE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RESUME, _resume, schema=_BASE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CANCEL, _cancel, schema=_CANCEL_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_CLEAR_BED, _clear_bed, schema=_CLEAR_BED_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SEND_GCODE, _send_gcode, schema=_SEND_GCODE_SCHEMA
    )


def async_unload_services(hass: HomeAssistant) -> None:
    """Remove SimplyPrint services."""
    for service in (
        SERVICE_PAUSE,
        SERVICE_RESUME,
        SERVICE_CANCEL,
        SERVICE_CLEAR_BED,
        SERVICE_SEND_GCODE,
    ):
        hass.services.async_remove(DOMAIN, service)
