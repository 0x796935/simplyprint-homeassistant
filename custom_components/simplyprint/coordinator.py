"""Data update coordinator for SimplyPrint."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    SimplyPrintApiClient,
    SimplyPrintApiError,
    SimplyPrintAuthError,
)
from .const import (
    CONF_ENABLE_STATISTICS,
    CONF_SCAN_INTERVAL,
    CONF_STATISTICS_DAYS,
    DEFAULT_ENABLE_STATISTICS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STATISTICS_DAYS,
    DOMAIN,
    STATE_PAUSED,
    STATE_PAUSING,
    STATE_PRINTING,
    STATE_RESUMING,
)
from .helpers import job_filename

# Printer states during which a file is actively loaded for a print.
_ACTIVE_PRINT_STATES = frozenset(
    {STATE_PRINTING, STATE_PAUSED, STATE_PAUSING, STATE_RESUMING}
)

_LOGGER = logging.getLogger(__name__)


class SimplyPrintCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate a single ``printers/Get`` poll plus optional statistics."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SimplyPrintApiClient,
    ) -> None:
        """Initialise the coordinator."""
        self.entry = entry
        self.client = client
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        # Stats are fetched once and then refreshed only periodically to stay
        # well within the 60 requests/min budget.
        self._stats_countdown = 0
        # Cache of filename -> {"url", "analysis", "file_id", "filename"} so the
        # gcode render is resolved at most once per distinct print file.
        self._render_cache: dict[str, dict[str, Any]] = {}

    @property
    def _enable_statistics(self) -> bool:
        return self.entry.options.get(
            CONF_ENABLE_STATISTICS, DEFAULT_ENABLE_STATISTICS
        )

    @property
    def _statistics_days(self) -> int:
        return self.entry.options.get(
            CONF_STATISTICS_DAYS, DEFAULT_STATISTICS_DAYS
        )

    @property
    def printer_ids(self) -> list[int]:
        """Return the printer ids currently known to the coordinator."""
        if not self.data:
            return []
        return list(self.data.get("printers", {}).keys())

    def get_printer(self, pid: int) -> dict[str, Any] | None:
        """Return the raw printer row for ``pid`` (the ``data[]`` element)."""
        if not self.data:
            return None
        return self.data.get("printers", {}).get(pid)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch fresh printer state (and statistics when enabled)."""
        try:
            response = await self.client.async_get_printers()
        except SimplyPrintAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SimplyPrintApiError as err:
            raise UpdateFailed(str(err)) from err

        rows = response.get("data") or []
        printers: dict[int, dict[str, Any]] = {}
        for row in rows:
            pid = row.get("id")
            if pid is not None:
                printers[pid] = row

        # Aggregate account-level counts straight from the printer list so we
        # don't spend extra API calls on them.
        total = len(printers)
        online = 0
        printing = 0
        operational = 0
        for row in printers.values():
            printer = row.get("printer") or {}
            if printer.get("online"):
                online += 1
            state = printer.get("state")
            if state == STATE_PRINTING:
                printing += 1
            elif state == "operational":
                operational += 1

        data: dict[str, Any] = {
            "printers": printers,
            "account": {
                "total_printers": total,
                "online_printers": online,
                "printing_printers": printing,
                "operational_printers": operational,
            },
            "statistics": self.data.get("statistics") if self.data else None,
        }

        # Best-effort: attach the gcode render + analysis for active prints.
        # Never let this break the core poll.
        try:
            await self._async_attach_renders(printers)
        except Exception as err:  # noqa: BLE001 - render data is non-critical
            _LOGGER.debug("Could not attach print renders: %s", err)

        if self._enable_statistics:
            if self._stats_countdown <= 0:
                stats = await self._async_fetch_statistics()
                if stats is not None:
                    data["statistics"] = stats
                # Refresh stats roughly every 5 minutes regardless of poll rate.
                interval_s = (self.update_interval or timedelta(seconds=30)).total_seconds()
                self._stats_countdown = max(1, int(300 / max(interval_s, 1)))
            else:
                self._stats_countdown -= 1
        else:
            data["statistics"] = None

        return data

    async def _async_attach_renders(self, printers: dict[int, dict[str, Any]]) -> None:
        """Resolve and attach the gcode render/analysis for printing jobs."""
        for row in printers.values():
            printer = row.get("printer") or {}
            if printer.get("state") not in _ACTIVE_PRINT_STATES:
                continue
            filename = job_filename(row.get("job"))
            if not filename:
                continue
            if filename not in self._render_cache:
                self._render_cache[filename] = await self._async_lookup_render(
                    filename
                )
            render = self._render_cache.get(filename)
            if render:
                row["render"] = render

    async def _async_lookup_render(self, filename: str) -> dict[str, Any]:
        """Find a file matching ``filename`` and return its render + analysis."""
        # Files are stored without their extension in ``name``; search on the
        # stem for the best chance of a match.
        stem = filename.rsplit(".", 1)[0]
        try:
            response = await self.client.async_get_files(search=stem)
        except SimplyPrintApiError as err:
            _LOGGER.debug("Render lookup failed for %s: %s", filename, err)
            return {}

        files = response.get("files") or []
        best: dict[str, Any] | None = None
        for candidate in files:
            name = candidate.get("name")
            if name and (name == stem or filename.startswith(name)):
                best = candidate
                break
        if best is None and files:
            best = files[0]

        if not best or not best.get("thumbnailUrl"):
            return {}
        return {
            "url": best.get("thumbnailUrl"),
            "analysis": best.get("gcodeAnalysis") or {},
            "file_id": best.get("id"),
            "filename": filename,
        }

    async def _async_fetch_statistics(self) -> dict[str, Any] | None:
        """Fetch account statistics; never fail the whole update over them."""
        now = dt_util.utcnow()
        start = int((now - timedelta(days=self._statistics_days)).timestamp())
        end = int(now.timestamp())
        try:
            response = await self.client.async_get_statistics(start, end)
        except SimplyPrintApiError as err:
            # Statistics require the Pro plan; degrade gracefully if unavailable.
            _LOGGER.debug("Could not fetch SimplyPrint statistics: %s", err)
            return None
        return response.get("data")
