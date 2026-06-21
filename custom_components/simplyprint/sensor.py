"""Sensor platform for SimplyPrint."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfMass,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ENABLE_STATISTICS,
    DEFAULT_ENABLE_STATISTICS,
    DOMAIN,
    PRINTER_STATES,
)
from .coordinator import SimplyPrintCoordinator
from .entity import SimplyPrintAccountEntity, SimplyPrintPrinterEntity
from . import helpers as h


def _active_tool_temp(printer: dict[str, Any], kind: str) -> float | None:
    """Return current/target temperature of the active tool."""
    temps = printer.get("temps") or {}
    bucket = temps.get(kind) or {}
    tools = bucket.get("tool")
    if not isinstance(tools, list) or not tools:
        return None
    idx = printer.get("activeExtruder")
    if not isinstance(idx, int) or idx < 0 or idx >= len(tools):
        idx = 0
    value = tools[idx]
    return float(value) if isinstance(value, (int, float)) else None


def _bed_temp(printer: dict[str, Any], kind: str) -> float | None:
    temps = printer.get("temps") or {}
    value = (temps.get(kind) or {}).get("bed")
    return float(value) if isinstance(value, (int, float)) else None


def _estimated_finish(entity: SimplyPrintPrinterEntity) -> datetime | None:
    job = entity.job
    if not job:
        return None
    left = h.job_time_left(job)
    if left is None:
        return None
    return dt_util.utcnow() + timedelta(seconds=left)


@dataclass(frozen=True, kw_only=True)
class SimplyPrintPrinterSensorDescription(SensorEntityDescription):
    """Describes a SimplyPrint printer sensor."""

    value_fn: Callable[[SimplyPrintPrinterEntity], StateType | datetime]


@dataclass(frozen=True, kw_only=True)
class SimplyPrintAccountSensorDescription(SensorEntityDescription):
    """Describes a SimplyPrint account sensor."""

    value_fn: Callable[[SimplyPrintCoordinator], StateType]
    needs_statistics: bool = False


PRINTER_SENSORS: tuple[SimplyPrintPrinterSensorDescription, ...] = (
    SimplyPrintPrinterSensorDescription(
        key="status",
        translation_key="status",
        icon="mdi:printer-3d",
        device_class=SensorDeviceClass.ENUM,
        options=PRINTER_STATES,
        value_fn=lambda e: (e.printer.get("state") or "unknown")
        if (e.printer.get("state") in PRINTER_STATES)
        else "unknown",
    ),
    SimplyPrintPrinterSensorDescription(
        key="progress",
        translation_key="progress",
        icon="mdi:progress-helper",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda e: h.job_progress(e.job),
    ),
    SimplyPrintPrinterSensorDescription(
        key="nozzle_temperature",
        translation_key="nozzle_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda e: _active_tool_temp(e.printer, "current"),
    ),
    SimplyPrintPrinterSensorDescription(
        key="nozzle_target_temperature",
        translation_key="nozzle_target_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        suggested_display_precision=0,
        value_fn=lambda e: _active_tool_temp(e.printer, "target"),
    ),
    SimplyPrintPrinterSensorDescription(
        key="bed_temperature",
        translation_key="bed_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda e: _bed_temp(e.printer, "current"),
    ),
    SimplyPrintPrinterSensorDescription(
        key="bed_target_temperature",
        translation_key="bed_target_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        suggested_display_precision=0,
        value_fn=lambda e: _bed_temp(e.printer, "target"),
    ),
    SimplyPrintPrinterSensorDescription(
        key="ambient_temperature",
        translation_key="ambient_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        suggested_display_precision=1,
        value_fn=lambda e: (
            float((e.printer.get("temps") or {}).get("ambient"))
            if isinstance((e.printer.get("temps") or {}).get("ambient"), (int, float))
            else None
        ),
    ),
    SimplyPrintPrinterSensorDescription(
        key="job_name",
        translation_key="job_name",
        icon="mdi:file-document-outline",
        value_fn=lambda e: h.job_filename(e.job),
    ),
    SimplyPrintPrinterSensorDescription(
        key="time_remaining",
        translation_key="time_remaining",
        icon="mdi:timer-sand",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda e: h.job_time_left(e.job),
    ),
    SimplyPrintPrinterSensorDescription(
        key="time_elapsed",
        translation_key="time_elapsed",
        icon="mdi:timer-outline",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        entity_registry_enabled_default=False,
        value_fn=lambda e: h.job_time_elapsed(e.job),
    ),
    SimplyPrintPrinterSensorDescription(
        key="estimated_finish",
        translation_key="estimated_finish",
        icon="mdi:clock-end",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_estimated_finish,
    ),
    SimplyPrintPrinterSensorDescription(
        key="layer",
        translation_key="layer",
        icon="mdi:layers-triple",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda e: h.job_layer(e.job),
    ),
    SimplyPrintPrinterSensorDescription(
        key="total_layers",
        translation_key="total_layers",
        icon="mdi:layers-triple-outline",
        value_fn=lambda e: (
            ((e.printer_row or {}).get("render") or {}).get("analysis", {})
        ).get("totalLayers"),
    ),
    SimplyPrintPrinterSensorDescription(
        key="filament_type",
        translation_key="filament_type",
        icon="mdi:printer-3d-nozzle",
        value_fn=lambda e: (
            (h.primary_filament(e.filament) or {}).get("type", {}).get("name")
            if isinstance((h.primary_filament(e.filament) or {}).get("type"), dict)
            else None
        ),
    ),
    SimplyPrintPrinterSensorDescription(
        key="filament_color",
        translation_key="filament_color",
        icon="mdi:palette",
        value_fn=lambda e: (h.primary_filament(e.filament) or {}).get("colorName"),
    ),
    SimplyPrintPrinterSensorDescription(
        key="filament_remaining",
        translation_key="filament_remaining",
        icon="mdi:gauge",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda e: h.filament_remaining_percent(h.primary_filament(e.filament)),
    ),
    SimplyPrintPrinterSensorDescription(
        key="host_memory",
        translation_key="host_memory",
        icon="mdi:memory",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda e: (e.printer.get("health") or {}).get("memory"),
    ),
    SimplyPrintPrinterSensorDescription(
        key="host_usage",
        translation_key="host_usage",
        icon="mdi:cpu-64-bit",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda e: (e.printer.get("health") or {}).get("usage"),
    ),
    SimplyPrintPrinterSensorDescription(
        key="latency",
        translation_key="latency",
        icon="mdi:speedometer",
        native_unit_of_measurement="ms",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda e: e.printer.get("latency"),
    ),
)


ACCOUNT_SENSORS: tuple[SimplyPrintAccountSensorDescription, ...] = (
    SimplyPrintAccountSensorDescription(
        key="total_printers",
        translation_key="total_printers",
        icon="mdi:printer-3d",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: (c.data or {}).get("account", {}).get("total_printers"),
    ),
    SimplyPrintAccountSensorDescription(
        key="online_printers",
        translation_key="online_printers",
        icon="mdi:printer-3d",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: (c.data or {}).get("account", {}).get("online_printers"),
    ),
    SimplyPrintAccountSensorDescription(
        key="printing_printers",
        translation_key="printing_printers",
        icon="mdi:printer-3d-nozzle",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: (c.data or {}).get("account", {}).get("printing_printers"),
    ),
    SimplyPrintAccountSensorDescription(
        key="total_print_time",
        translation_key="total_print_time",
        icon="mdi:timer",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        needs_statistics=True,
        value_fn=lambda c: _stat_hours(c, "total_print_seconds"),
    ),
    SimplyPrintAccountSensorDescription(
        key="total_filament_usage",
        translation_key="total_filament_usage",
        icon="mdi:printer-3d-nozzle",
        native_unit_of_measurement=UnitOfMass.GRAMS,
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        needs_statistics=True,
        value_fn=lambda c: _stat(c, "total_filament_usage_gram"),
    ),
    SimplyPrintAccountSensorDescription(
        key="print_job_count",
        translation_key="print_job_count",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL_INCREASING,
        needs_statistics=True,
        value_fn=lambda c: _stat(c, "print_job_count"),
    ),
    SimplyPrintAccountSensorDescription(
        key="done_print_jobs",
        translation_key="done_print_jobs",
        icon="mdi:check-circle-outline",
        state_class=SensorStateClass.TOTAL_INCREASING,
        needs_statistics=True,
        value_fn=lambda c: _stat(c, "done_print_jobs"),
    ),
    SimplyPrintAccountSensorDescription(
        key="failed_print_jobs",
        translation_key="failed_print_jobs",
        icon="mdi:alert-circle-outline",
        state_class=SensorStateClass.TOTAL_INCREASING,
        needs_statistics=True,
        value_fn=lambda c: _stat(c, "failed_print_jobs"),
    ),
)


def _stat(coordinator: SimplyPrintCoordinator, key: str) -> StateType:
    stats = (coordinator.data or {}).get("statistics")
    if not isinstance(stats, dict):
        return None
    return stats.get(key)


def _stat_hours(coordinator: SimplyPrintCoordinator, key: str) -> StateType:
    value = _stat(coordinator, key)
    if value is None:
        return None
    try:
        return round(float(value) / 3600, 2)
    except (TypeError, ValueError):
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SimplyPrint sensors."""
    coordinator: SimplyPrintCoordinator = hass.data[DOMAIN][entry.entry_id]

    stats_enabled = entry.options.get(
        CONF_ENABLE_STATISTICS, DEFAULT_ENABLE_STATISTICS
    )
    async_add_entities(
        SimplyPrintAccountSensor(coordinator, desc)
        for desc in ACCOUNT_SENSORS
        if stats_enabled or not desc.needs_statistics
    )

    known: set[int] = set()

    @callback
    def _add_printers() -> None:
        new: list[SimplyPrintPrinterSensor] = []
        for pid in coordinator.printer_ids:
            if pid in known:
                continue
            known.add(pid)
            new.extend(
                SimplyPrintPrinterSensor(coordinator, pid, desc)
                for desc in PRINTER_SENSORS
            )
        if new:
            async_add_entities(new)

    _add_printers()
    entry.async_on_unload(coordinator.async_add_listener(_add_printers))


class SimplyPrintPrinterSensor(SimplyPrintPrinterEntity, SensorEntity):
    """A sensor bound to a single printer."""

    entity_description: SimplyPrintPrinterSensorDescription

    def __init__(
        self,
        coordinator: SimplyPrintCoordinator,
        pid: int,
        description: SimplyPrintPrinterSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, pid)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{pid}_{description.key}"

    @property
    def native_value(self) -> StateType | datetime:
        """Return the sensor value."""
        if self.printer_row is None:
            return None
        return self.entity_description.value_fn(self)


class SimplyPrintAccountSensor(SimplyPrintAccountEntity, SensorEntity):
    """An account-level aggregate / statistics sensor."""

    entity_description: SimplyPrintAccountSensorDescription

    def __init__(
        self,
        coordinator: SimplyPrintCoordinator,
        description: SimplyPrintAccountSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"{DOMAIN}_account_{self._company_id}_{description.key}"
        )

    @property
    def native_value(self) -> StateType:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator)
