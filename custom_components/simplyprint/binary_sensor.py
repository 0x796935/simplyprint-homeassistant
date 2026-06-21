"""Binary sensor platform for SimplyPrint."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, STATE_ERROR, STATE_PAUSED, STATE_PRINTING
from .coordinator import SimplyPrintCoordinator
from .entity import SimplyPrintPrinterEntity


@dataclass(frozen=True, kw_only=True)
class SimplyPrintBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a SimplyPrint binary sensor."""

    value_fn: Callable[[SimplyPrintPrinterEntity], bool | None]


BINARY_SENSORS: tuple[SimplyPrintBinarySensorDescription, ...] = (
    SimplyPrintBinarySensorDescription(
        key="online",
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda e: bool(e.printer.get("online")),
    ),
    SimplyPrintBinarySensorDescription(
        key="printing",
        translation_key="printing",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda e: e.printer.get("state") == STATE_PRINTING,
    ),
    SimplyPrintBinarySensorDescription(
        key="paused",
        translation_key="paused",
        icon="mdi:pause-circle",
        value_fn=lambda e: e.printer.get("state") == STATE_PAUSED,
    ),
    SimplyPrintBinarySensorDescription(
        key="error",
        translation_key="error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda e: e.printer.get("state") == STATE_ERROR,
    ),
    SimplyPrintBinarySensorDescription(
        key="awaiting_bed_clear",
        translation_key="awaiting_bed_clear",
        icon="mdi:broom",
        value_fn=lambda e: bool(e.printer.get("awaitingBedClear")),
    ),
    SimplyPrintBinarySensorDescription(
        key="filament_sensor",
        translation_key="filament_sensor",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_registry_enabled_default=False,
        value_fn=lambda e: (
            bool(e.printer.get("filSensor"))
            if e.printer.get("hasFilSensor")
            else None
        ),
    ),
    SimplyPrintBinarySensorDescription(
        key="out_of_order",
        translation_key="out_of_order",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda e: bool(e.printer.get("outOfOrder")),
    ),
    SimplyPrintBinarySensorDescription(
        key="ai_enabled",
        translation_key="ai_enabled",
        icon="mdi:robot-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda e: bool(e.printer.get("aiEnabled")),
    ),
    SimplyPrintBinarySensorDescription(
        key="has_camera",
        translation_key="has_camera",
        icon="mdi:camera",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda e: bool(e.printer.get("hasCam")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SimplyPrint binary sensors."""
    coordinator: SimplyPrintCoordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[int] = set()

    @callback
    def _add_printers() -> None:
        new: list[SimplyPrintBinarySensor] = []
        for pid in coordinator.printer_ids:
            if pid in known:
                continue
            known.add(pid)
            new.extend(
                SimplyPrintBinarySensor(coordinator, pid, desc)
                for desc in BINARY_SENSORS
            )
        if new:
            async_add_entities(new)

    _add_printers()
    entry.async_on_unload(coordinator.async_add_listener(_add_printers))


class SimplyPrintBinarySensor(SimplyPrintPrinterEntity, BinarySensorEntity):
    """A binary sensor bound to a single printer."""

    entity_description: SimplyPrintBinarySensorDescription

    def __init__(
        self,
        coordinator: SimplyPrintCoordinator,
        pid: int,
        description: SimplyPrintBinarySensorDescription,
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, pid)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{pid}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return the binary state."""
        if self.printer_row is None:
            return None
        return self.entity_description.value_fn(self)
