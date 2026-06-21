"""Thin async client for the SimplyPrint REST API.

All SimplyPrint endpoints are POST requests under ``/{company_id}/`` and
authenticate with an ``X-API-KEY`` header. Responses are JSON objects that
always carry a top-level ``status`` boolean and a ``message`` string that is
populated on failure.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession

from .const import DEFAULT_BASE_URL

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30

# SimplyPrint's WAF rejects the bare ``Python-urllib`` User-Agent with a 403.
# Home Assistant's shared aiohttp session already sends a fine UA, but we set an
# explicit one so the client works regardless of the session it is given.
USER_AGENT = "HomeAssistant-SimplyPrint/1.0"


class SimplyPrintApiError(Exception):
    """Generic SimplyPrint API error."""


class SimplyPrintAuthError(SimplyPrintApiError):
    """Raised when the API key/company id is rejected."""


class SimplyPrintRateLimitError(SimplyPrintApiError):
    """Raised when the account hits the API rate limit (60 req/min)."""


class SimplyPrintApiClient:
    """Minimal async wrapper around the endpoints this integration uses."""

    def __init__(
        self,
        session: ClientSession,
        api_key: str,
        company_id: str | int,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        """Initialise the client."""
        self._session = session
        self._api_key = api_key
        self._company_id = str(company_id).strip()
        self._base_url = base_url.rstrip("/")

    @property
    def company_id(self) -> str:
        """Return the configured company id."""
        return self._company_id

    def _url(self, endpoint: str) -> str:
        return f"{self._base_url}/{self._company_id}/{endpoint.lstrip('/')}"

    async def _request(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform a POST request and return the decoded JSON payload."""
        headers = {
            "X-API-KEY": self._api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                response = await self._session.post(
                    self._url(endpoint),
                    headers=headers,
                    params=params,
                    json=body if body is not None else {},
                )
        except (TimeoutError, asyncio.TimeoutError) as err:
            raise SimplyPrintApiError(
                f"Timeout talking to SimplyPrint ({endpoint})"
            ) from err
        except ClientError as err:
            raise SimplyPrintApiError(
                f"Connection error talking to SimplyPrint ({endpoint}): {err}"
            ) from err

        if response.status in (401, 403):
            raise SimplyPrintAuthError(
                "SimplyPrint rejected the API key or company id "
                f"(HTTP {response.status})"
            )
        if response.status == 429:
            raise SimplyPrintRateLimitError(
                "SimplyPrint rate limit reached (60 requests/min)"
            )

        try:
            response.raise_for_status()
        except ClientResponseError as err:
            raise SimplyPrintApiError(
                f"SimplyPrint returned HTTP {response.status} for {endpoint}"
            ) from err

        try:
            data: dict[str, Any] = await response.json()
        except (ValueError, ClientError) as err:
            raise SimplyPrintApiError(
                f"SimplyPrint returned a non-JSON response for {endpoint}"
            ) from err

        if not isinstance(data, dict):
            raise SimplyPrintApiError(
                f"Unexpected response shape from SimplyPrint for {endpoint}"
            )

        if data.get("status") is False:
            message = data.get("message") or "Unknown error"
            # An invalid key surfaces as status=false on company-scoped routes.
            lowered = str(message).lower()
            if "api key" in lowered or "unauthor" in lowered or "permission" in lowered:
                raise SimplyPrintAuthError(message)
            raise SimplyPrintApiError(message)

        return data

    # -- Auth / account ---------------------------------------------------

    async def async_test(self) -> dict[str, Any]:
        """Validate the API key + company id pair."""
        return await self._request("account/Test")

    async def async_get_user(self) -> dict[str, Any]:
        """Return the authenticated user's details."""
        return await self._request("account/GetUser")

    async def async_get_statistics(
        self,
        start_date: int,
        end_date: int,
        printers: list[int] | None = None,
    ) -> dict[str, Any]:
        """Return account statistics for the given unix-second window."""
        body: dict[str, Any] = {
            "start_date": str(start_date),
            "end_date": str(end_date),
        }
        if printers:
            body["printers"] = printers
        return await self._request("account/GetStatistics", body=body)

    # -- Files ------------------------------------------------------------

    async def async_get_files(
        self,
        *,
        search: str | None = None,
        global_search: bool = True,
        folder: int = 0,
    ) -> dict[str, Any]:
        """Search files (used to resolve a print's gcode render + analysis)."""
        params: dict[str, Any] = {"f": folder}
        if global_search:
            params["global_search"] = "true"
        if search:
            params["search"] = search
        return await self._request("files/GetFiles", params=params)

    # -- Printers ---------------------------------------------------------

    async def async_get_printers(
        self, page: int = 1, page_size: int = 100
    ) -> dict[str, Any]:
        """Return all printers with their current job + filament state."""
        return await self._request(
            "printers/Get", body={"page": page, "page_size": page_size}
        )

    # -- Printer actions --------------------------------------------------

    async def async_pause(self, pid: int) -> dict[str, Any]:
        """Pause an active print on the given printer."""
        return await self._request(
            "printers/actions/Pause", params={"pid": pid}
        )

    async def async_resume(self, pid: int) -> dict[str, Any]:
        """Resume a paused print on the given printer."""
        return await self._request(
            "printers/actions/Resume", params={"pid": pid}
        )

    async def async_cancel(
        self,
        pid: int,
        *,
        reason: int | None = None,
        comment: str | None = None,
        return_to_queue: bool | None = None,
        return_position: str | None = None,
    ) -> dict[str, Any]:
        """Cancel an active print on the given printer."""
        body: dict[str, Any] = {}
        if reason is not None:
            body["reason"] = reason
        if comment is not None:
            body["comment"] = comment
        if return_to_queue is not None:
            body["return_to_queue"] = return_to_queue
        if return_position is not None:
            body["return_position"] = return_position
        return await self._request(
            "printers/actions/Cancel", params={"pid": pid}, body=body
        )

    async def async_clear_bed(
        self,
        pid: int,
        *,
        success: bool | None = None,
        rating: int | None = None,
    ) -> dict[str, Any]:
        """Mark a printer's bed as cleared after a finished print."""
        body: dict[str, Any] = {}
        if success is not None:
            body["success"] = success
        if rating is not None:
            body["rating"] = rating
        return await self._request(
            "printers/actions/ClearBed", params={"pid": pid}, body=body
        )

    async def async_send_gcode(
        self,
        pid: int,
        *,
        gcode: list[str] | None = None,
        macro: str | None = None,
    ) -> dict[str, Any]:
        """Send raw G-code or a named macro to a printer (Print Farm plan)."""
        body: dict[str, Any] = {}
        if gcode:
            body["gcode"] = gcode
        if macro:
            body["macro"] = macro
        return await self._request(
            "printers/actions/SendGcode", params={"pid": pid}, body=body
        )
