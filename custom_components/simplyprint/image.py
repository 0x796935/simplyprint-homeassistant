"""Image platform for SimplyPrint — the gcode render of the current print."""

from __future__ import annotations

from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import SimplyPrintCoordinator
from .entity import SimplyPrintPrinterEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SimplyPrint print-render image entities."""
    coordinator: SimplyPrintCoordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[int] = set()

    @callback
    def _add_printers() -> None:
        new: list[SimplyPrintRenderImage] = []
        for pid in coordinator.printer_ids:
            if pid in known:
                continue
            known.add(pid)
            new.append(SimplyPrintRenderImage(coordinator, pid))
        if new:
            async_add_entities(new)

    _add_printers()
    entry.async_on_unload(coordinator.async_add_listener(_add_printers))


class SimplyPrintRenderImage(SimplyPrintPrinterEntity, ImageEntity):
    """Slicer/gcode render of the file currently printing."""

    _attr_translation_key = "print_render"
    _attr_content_type = "image/png"

    def __init__(self, coordinator: SimplyPrintCoordinator, pid: int) -> None:
        """Initialise the image entity."""
        SimplyPrintPrinterEntity.__init__(self, coordinator, pid)
        ImageEntity.__init__(self, coordinator.hass)
        self._attr_unique_id = f"{DOMAIN}_{pid}_print_render"
        self._current_url: str | None = self._render_url
        if self._current_url:
            self._attr_image_last_updated = dt_util.utcnow()

    @property
    def _render(self) -> dict[str, Any]:
        return (self.printer_row or {}).get("render") or {}

    @property
    def _render_url(self) -> str | None:
        return self._render.get("url")

    @property
    def image_url(self) -> str | None:
        """Return the public CDN URL of the current print's render."""
        return self._render_url

    @property
    def available(self) -> bool:
        """Available only while a render is resolved for the active print."""
        return super().available and self._render_url is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the gcode analysis alongside the render."""
        analysis = self._render.get("analysis") or {}
        if not analysis and not self._render:
            return None
        return {
            "filename": self._render.get("filename"),
            "slicer": analysis.get("slicer"),
            "total_layers": analysis.get("totalLayers"),
            "layer_height": analysis.get("layerHeight"),
            "model_size": analysis.get("modelSize"),
            "estimated_print_time": analysis.get("estimate"),
            "nozzle_size": analysis.get("nozzleSize"),
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Refresh the image timestamp when the render URL changes."""
        url = self._render_url
        if url != self._current_url:
            self._current_url = url
            if url is not None:
                self._attr_image_last_updated = dt_util.utcnow()
        super()._handle_coordinator_update()
