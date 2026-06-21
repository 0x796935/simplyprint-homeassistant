"""Base entities for SimplyPrint."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ACCOUNT_DEVICE_PREFIX,
    DOMAIN,
    MANUFACTURER,
    PANEL_URL,
    PRINTER_DEVICE_PREFIX,
)
from .coordinator import SimplyPrintCoordinator


def account_device_id(company_id: str) -> tuple[str, str]:
    """Return the device identifier tuple for the account device."""
    return (DOMAIN, f"{ACCOUNT_DEVICE_PREFIX}_{company_id}")


def printer_device_id(pid: int) -> tuple[str, str]:
    """Return the device identifier tuple for a printer device."""
    return (DOMAIN, f"{PRINTER_DEVICE_PREFIX}_{pid}")


class SimplyPrintAccountEntity(CoordinatorEntity[SimplyPrintCoordinator]):
    """Base entity attached to the account-level device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SimplyPrintCoordinator) -> None:
        """Initialise the account entity."""
        super().__init__(coordinator)
        self._company_id = coordinator.client.company_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return the account device info."""
        return DeviceInfo(
            identifiers={account_device_id(self._company_id)},
            manufacturer=MANUFACTURER,
            name=f"SimplyPrint ({self._company_id})",
            model="Account",
            configuration_url=PANEL_URL,
            entry_type=None,
        )


class SimplyPrintPrinterEntity(CoordinatorEntity[SimplyPrintCoordinator]):
    """Base entity attached to a printer device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SimplyPrintCoordinator, pid: int) -> None:
        """Initialise the printer entity."""
        super().__init__(coordinator)
        self._pid = pid
        self._company_id = coordinator.client.company_id

    @property
    def printer_row(self) -> dict[str, Any] | None:
        """Return the full printer row (``id``/``printer``/``job``/...)."""
        return self.coordinator.get_printer(self._pid)

    @property
    def printer(self) -> dict[str, Any]:
        """Return the ``printer`` sub-object (never ``None`` for safety)."""
        row = self.printer_row
        return (row or {}).get("printer") or {}

    @property
    def job(self) -> dict[str, Any] | None:
        """Return the current ``job`` object, if any."""
        row = self.printer_row
        if not row:
            return None
        return row.get("job")

    @property
    def filament(self) -> dict[str, Any] | None:
        """Return the assigned ``filament`` mapping (keyed by extruder)."""
        row = self.printer_row
        if not row:
            return None
        return row.get("filament")

    @property
    def available(self) -> bool:
        """Entity is available while the printer is present in the poll."""
        return (
            self.coordinator.last_update_success
            and self.printer_row is not None
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return the printer device info."""
        printer = self.printer
        model = printer.get("model") or {}
        brand = model.get("brand") or MANUFACTURER
        model_name = model.get("name") or printer.get("api") or "Printer"
        return DeviceInfo(
            identifiers={printer_device_id(self._pid)},
            manufacturer=brand,
            model=model_name,
            name=printer.get("name") or f"Printer {self._pid}",
            sw_version=printer.get("firmwareVersion") or printer.get("firmware"),
            configuration_url=PANEL_URL,
            via_device=account_device_id(self._company_id),
        )
