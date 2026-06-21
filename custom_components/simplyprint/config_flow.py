"""Config and options flow for SimplyPrint."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    SimplyPrintApiClient,
    SimplyPrintApiError,
    SimplyPrintAuthError,
    SimplyPrintRateLimitError,
)
from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_COMPANY_ID,
    CONF_ENABLE_STATISTICS,
    CONF_SCAN_INTERVAL,
    CONF_STATISTICS_DAYS,
    DEFAULT_BASE_URL,
    DEFAULT_ENABLE_STATISTICS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STATISTICS_DAYS,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


async def _validate(
    hass, api_key: str, company_id: str, base_url: str
) -> tuple[str | None, str | None]:
    """Validate credentials. Returns ``(account_name, error_code)``."""
    session = aiohttp_client.async_get_clientsession(hass)
    client = SimplyPrintApiClient(session, api_key, company_id, base_url)
    try:
        await client.async_test()
        user = await client.async_get_user()
    except SimplyPrintAuthError:
        return None, "invalid_auth"
    except SimplyPrintRateLimitError:
        return None, "rate_limited"
    except SimplyPrintApiError:
        return None, "cannot_connect"
    name = None
    if isinstance(user, dict):
        name = (user.get("user") or {}).get("name")
    return name, None


class SimplyPrintConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the SimplyPrint config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise."""
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            company_id = str(user_input[CONF_COMPANY_ID]).strip()
            base_url = user_input.get(CONF_BASE_URL, DEFAULT_BASE_URL).strip()

            await self.async_set_unique_id(company_id)
            self._abort_if_unique_id_configured()

            name, error = await _validate(self.hass, api_key, company_id, base_url)
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=name or f"SimplyPrint ({company_id})",
                    data={
                        CONF_API_KEY: api_key,
                        CONF_COMPANY_ID: company_id,
                        CONF_BASE_URL: base_url,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Required(CONF_COMPANY_ID): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Optional(
                        CONF_BASE_URL, default=DEFAULT_BASE_URL
                    ): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when the API key stops working."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm re-authentication with a fresh API key."""
        errors: dict[str, str] = {}
        assert self._reauth_entry is not None
        company_id = self._reauth_entry.data[CONF_COMPANY_ID]
        base_url = self._reauth_entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL)

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            _name, error = await _validate(self.hass, api_key, company_id, base_url)
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    self._reauth_entry,
                    data={**self._reauth_entry.data, CONF_API_KEY: api_key},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            description_placeholders={"company_id": company_id},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> SimplyPrintOptionsFlow:
        """Return the options flow handler."""
        return SimplyPrintOptionsFlow()


class SimplyPrintOptionsFlow(OptionsFlow):
    """Handle SimplyPrint options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    CONF_ENABLE_STATISTICS: user_input[CONF_ENABLE_STATISTICS],
                    CONF_STATISTICS_DAYS: int(user_input[CONF_STATISTICS_DAYS]),
                }
            )

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            max=MAX_SCAN_INTERVAL,
                            step=5,
                            unit_of_measurement="s",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_ENABLE_STATISTICS,
                        default=options.get(
                            CONF_ENABLE_STATISTICS, DEFAULT_ENABLE_STATISTICS
                        ),
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_STATISTICS_DAYS,
                        default=options.get(
                            CONF_STATISTICS_DAYS, DEFAULT_STATISTICS_DAYS
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=365,
                            step=1,
                            unit_of_measurement="days",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
        )
