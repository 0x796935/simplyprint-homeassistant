"""Fixtures for the SimplyPrint tests."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Pre-import the integration's modules in the main thread so Home Assistant's
# loader doesn't pull them in via the import_executor mid-test (whose shutdown
# watchdog daemon otherwise trips the strict teardown thread check).
import custom_components.simplyprint  # noqa: F401,E402
import custom_components.simplyprint.binary_sensor  # noqa: F401,E402
import custom_components.simplyprint.button  # noqa: F401,E402
import custom_components.simplyprint.config_flow  # noqa: F401,E402
import custom_components.simplyprint.sensor  # noqa: F401,E402

from custom_components.simplyprint.const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_COMPANY_ID,
    DEFAULT_BASE_URL,
    DOMAIN,
)

COMPANY_ID = "76283"
BASE = f"{DEFAULT_BASE_URL}/{COMPANY_ID}"


# Two printers: one actively printing (to exercise job sensors), one idle.
FAKE_PRINTERS = [
    {
        "id": 50051,
        "sort_order": 0,
        "printer": {
            "name": "Bambu Lab P1S Combo",
            "state": "printing",
            "online": True,
            "api": "Bambu",
            "firmwareVersion": "01.09.01.00",
            "firmware": "Bambu OTA",
            "activeExtruder": 0,
            "hasCam": 1,
            "hasFilSensor": False,
            "filSensor": False,
            "aiEnabled": True,
            "awaitingBedClear": False,
            "outOfOrder": 0,
            "temps": {
                "ambient": 28,
                "current": {"tool": [215], "bed": 60},
                "target": {"tool": [220], "bed": 60},
            },
            "health": {"usage": 5, "temp": 0, "memory": 55},
            "latency": 42,
            "model": {
                "id": 478,
                "name": "P1S Combo",
                "brand": "Bambu Lab",
            },
        },
        "filament": {
            "0": {
                "type": {"id": 1, "name": "PLA"},
                "colorName": "Bright Green",
                "colorHex": "#0ACC38",
                "total": 1000,
                "left": 800,
            }
        },
        "job": {
            "filename": "benchy.gcode",
            "currentPercentage": 42,
            "timeLeft": 600,
            "printTime": 300,
            "startDate": "2026-06-21T10:00:00+00:00",
            "layer": 12,
            "totalLayers": 80,
            "filUsageGram": 4.2,
        },
        "notifications": [],
    },
    {
        "id": 51887,
        "sort_order": 1,
        "printer": {
            "name": "Voron 2.4",
            "state": "operational",
            "online": True,
            "api": "Klipper",
            "firmwareVersion": "v0.12.0",
            "activeExtruder": 0,
            "hasCam": 1,
            "aiEnabled": False,
            "awaitingBedClear": False,
            "outOfOrder": 0,
            "temps": {
                "ambient": 25,
                "current": {"tool": [27], "bed": 29},
                "target": {"tool": [0], "bed": 0},
            },
            "health": {"usage": 1, "temp": 0, "memory": 37},
            "model": {"name": "Voron 2.X", "brand": "Voron"},
        },
        "filament": {
            "0": {
                "type": {"id": 2, "name": "SUNLU PLA"},
                "colorName": "Pink",
                "total": 329962,
                "left": 320603.64,
            }
        },
        "job": None,
        "notifications": [],
    },
]


def mock_api(aioclient_mock, printers=None, statistics=None) -> None:
    """Register the SimplyPrint endpoints on the aiohttp mock."""
    aioclient_mock.post(
        f"{BASE}/account/Test",
        json={"status": True, "message": "Your API key is valid!"},
    )
    aioclient_mock.post(
        f"{BASE}/account/GetUser",
        json={"status": True, "user": {"id": 84447, "name": "yi5"}},
    )
    aioclient_mock.post(
        f"{BASE}/printers/Get",
        json={
            "status": True,
            "message": None,
            "total": len(printers if printers is not None else FAKE_PRINTERS),
            "data": printers if printers is not None else FAKE_PRINTERS,
        },
    )
    # File search used to resolve the gcode render + analysis for active prints.
    aioclient_mock.post(
        f"{BASE}/files/GetFiles",
        json={
            "status": True,
            "files": [
                {
                    "id": "benchyfileid",
                    "name": "benchy",
                    "ext": "gcode",
                    "thumbnailUrl": "https://cdn.simplyprint.io/i/user/file/benchyfileid.png",
                    "gcodeAnalysis": {
                        "totalLayers": 80,
                        "layerHeight": 0.2,
                        "slicer": "OrcaSlicer",
                        "estimate": 3600,
                        "modelSize": {"x": 60, "y": 31, "z": 48},
                        "nozzleSize": 0.4,
                    },
                }
            ],
        },
    )
    if statistics is not None:
        aioclient_mock.post(
            f"{BASE}/account/GetStatistics",
            json={"status": True, "data": statistics},
        )
    for action in ("Pause", "Resume", "Cancel", "ClearBed", "SendGcode"):
        aioclient_mock.post(
            f"{BASE}/printers/actions/{action}",
            json={"status": True, "message": None},
        )


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mocked config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=COMPANY_ID,
        title="SimplyPrint (76283)",
        data={
            CONF_API_KEY: "test-api-key",
            CONF_COMPANY_ID: COMPANY_ID,
            CONF_BASE_URL: DEFAULT_BASE_URL,
        },
    )


_WARM_RESOLVER = []


@pytest.fixture(scope="session", autouse=True)
def _warm_async_resolver():
    """Pre-spawn aiodns/pycares' long-lived daemon resolver thread.

    Home Assistant's shared aiohttp session uses ``aiohttp.AsyncResolver``,
    which starts a daemon thread on first use. Creating it once up front means
    the per-test thread-leak check records it in its baseline instead of
    blaming whichever test first opens a client session. Real timer/task leak
    detection is unaffected.
    """
    import asyncio

    import aiohttp

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        _WARM_RESOLVER.append(aiohttp.AsyncResolver())
    finally:
        asyncio.set_event_loop(None)
        loop.close()
    yield


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration in all tests."""
    yield


@pytest.fixture(autouse=True)
def _mock_storage(hass_storage):
    """Use in-memory config-entry storage so flows don't leave save threads."""
    yield
