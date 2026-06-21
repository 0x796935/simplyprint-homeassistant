"""Test the SimplyPrint config and options flow."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.simplyprint.const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_COMPANY_ID,
    CONF_ENABLE_STATISTICS,
    CONF_SCAN_INTERVAL,
    CONF_STATISTICS_DAYS,
    DEFAULT_BASE_URL,
    DOMAIN,
)

from .conftest import COMPANY_ID, mock_api


async def test_user_flow_success(hass: HomeAssistant) -> None:
    """A valid key + company id creates an entry (flow logic in isolation)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "custom_components.simplyprint.config_flow._validate",
        return_value=("yi5", None),
    ), patch(
        "custom_components.simplyprint.async_setup_entry", return_value=True
    ) as mock_setup:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_KEY: "test-api-key",
                CONF_COMPANY_ID: COMPANY_ID,
                CONF_BASE_URL: DEFAULT_BASE_URL,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "yi5"
    assert result["data"][CONF_API_KEY] == "test-api-key"
    assert result["data"][CONF_COMPANY_ID] == COMPANY_ID
    assert result["result"].unique_id == COMPANY_ID
    assert len(mock_setup.mock_calls) == 1


async def test_user_flow_invalid_auth(hass: HomeAssistant, aioclient_mock) -> None:
    """A rejected key surfaces invalid_auth."""
    aioclient_mock.post(
        f"{DEFAULT_BASE_URL}/{COMPANY_ID}/account/Test",
        status=403,
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_API_KEY: "bad",
            CONF_COMPANY_ID: COMPANY_ID,
            CONF_BASE_URL: DEFAULT_BASE_URL,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect(hass: HomeAssistant, aioclient_mock) -> None:
    """A status=false generic error surfaces cannot_connect."""
    aioclient_mock.post(
        f"{DEFAULT_BASE_URL}/{COMPANY_ID}/account/Test",
        json={"status": False, "message": "Service unavailable"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_API_KEY: "x",
            CONF_COMPANY_ID: COMPANY_ID,
            CONF_BASE_URL: DEFAULT_BASE_URL,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_duplicate_aborts(
    hass: HomeAssistant, aioclient_mock, mock_config_entry
) -> None:
    """Configuring the same company twice aborts."""
    mock_config_entry.add_to_hass(hass)
    mock_api(aioclient_mock)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_API_KEY: "test-api-key",
            CONF_COMPANY_ID: COMPANY_ID,
            CONF_BASE_URL: DEFAULT_BASE_URL,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow(
    hass: HomeAssistant, aioclient_mock, mock_config_entry
) -> None:
    """Reauth updates the stored API key."""
    mock_config_entry.add_to_hass(hass)
    mock_api(aioclient_mock)

    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "new-key"}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_API_KEY] == "new-key"

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()


async def test_options_flow(
    hass: HomeAssistant, aioclient_mock, mock_config_entry
) -> None:
    """The options flow stores poll interval + statistics settings."""
    mock_config_entry.add_to_hass(hass)
    mock_api(aioclient_mock)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(
        mock_config_entry.entry_id
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_SCAN_INTERVAL: 60,
            CONF_ENABLE_STATISTICS: True,
            CONF_STATISTICS_DAYS: 90,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options[CONF_SCAN_INTERVAL] == 60
    assert mock_config_entry.options[CONF_ENABLE_STATISTICS] is True
    assert mock_config_entry.options[CONF_STATISTICS_DAYS] == 90
