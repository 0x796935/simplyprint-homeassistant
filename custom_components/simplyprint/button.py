"""Button platform for SimplyPrint printer actions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import (
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import SimplyPrintApiClient, SimplyPrintApiError
from .const import DOMAIN
from .coordinator import SimplyPrintCoordinator
from .entity import SimplyPrintPrinterEntity


@dataclass(frozen=True, kw_only=True)
class SimplyPrintButtonDescription(ButtonEntityDescription):
    """Describes a SimplyPrint action button."""

    press_fn: Callable[[SimplyPrintApiClient, int], Awaitable]


BUTTONS: tuple[SimplyPrintButtonDescription, ...] = (
    SimplyPrintButtonDescription(
        key="pause",
        translation_key="pause",
        icon="mdi:pause",
        press_fn=lambda client, pid: client.async_pause(pid),
    ),
    SimplyPrintButtonDescription(
        key="resume",
        translation_key="resume",
        icon="mdi:play",
        press_fn=lambda client, pid: client.async_resume(pid),
    ),
    SimplyPrintButtonDescription(
        key="cancel",
        translation_key="cancel",
        icon="mdi:stop",
        press_fn=lambda client, pid: client.async_cancel(pid),
    ),
    SimplyPrintButtonDescription(
        key="clear_bed",
        translation_key="clear_bed",
        icon="mdi:broom",
        press_fn=lambda client, pid: client.async_clear_bed(pid, success=True),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SimplyPrint action buttons."""
    coordinator: SimplyPrintCoordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[int] = set()

    @callback
    def _add_printers() -> None:
        new: list[SimplyPrintButton] = []
        for pid in coordinator.printer_ids:
            if pid in known:
                continue
            known.add(pid)
            new.extend(
                SimplyPrintButton(coordinator, pid, desc) for desc in BUTTONS
            )
        if new:
            async_add_entities(new)

    _add_printers()
    entry.async_on_unload(coordinator.async_add_listener(_add_printers))


class SimplyPrintButton(SimplyPrintPrinterEntity, ButtonEntity):
    """An action button bound to a single printer."""

    entity_description: SimplyPrintButtonDescription

    def __init__(
        self,
        coordinator: SimplyPrintCoordinator,
        pid: int,
        description: SimplyPrintButtonDescription,
    ) -> None:
        """Initialise the button."""
        super().__init__(coordinator, pid)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{pid}_{description.key}"

    async def async_press(self) -> None:
        """Execute the printer action."""
        try:
            await self.entity_description.press_fn(self.coordinator.client, self._pid)
        except SimplyPrintApiError as err:
            raise HomeAssistantError(
                f"SimplyPrint {self.entity_description.key} failed: {err}"
            ) from err
        await self.coordinator.async_request_refresh()
