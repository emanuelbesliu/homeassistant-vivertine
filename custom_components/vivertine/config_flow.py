"""Config flow for the Vivertine Gym integration."""

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .api import VivertineAPI, VivertineApiError, VivertineAuthError
from .const import (
    DOMAIN,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_UPDATE_INTERVAL,
    CONF_FAVORITE_CLASSES,
    CONF_NOTIFY_SERVICE,
    CONF_LOW_SPOTS_THRESHOLD,
    DEFAULT_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
    MAX_UPDATE_INTERVAL,
    DEFAULT_LOW_SPOTS_THRESHOLD,
)

_LOGGER = logging.getLogger(__name__)


class VivertineConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vivertine Gym."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step — email/password login."""
        errors = {}

        if user_input is not None:
            # Prevent duplicate entries for the same email
            await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
            self._abort_if_unique_id_configured()

            api = VivertineAPI(
                email=user_input[CONF_EMAIL],
                password=user_input[CONF_PASSWORD],
            )
            try:
                await self.hass.async_add_executor_job(api.validate_connection)
            except VivertineAuthError:
                errors["base"] = "invalid_auth"
            except VivertineApiError:
                errors["base"] = "cannot_connect"
            finally:
                await self.hass.async_add_executor_job(api.close)

            if not errors:
                return self.async_create_entry(
                    title=f"Vivertine ({user_input[CONF_EMAIL]})",
                    data={
                        CONF_EMAIL: user_input[CONF_EMAIL],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_UPDATE_INTERVAL: user_input.get(
                            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                        ),
                    },
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=DEFAULT_UPDATE_INTERVAL,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL
                    ),
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return VivertineOptionsFlowHandler()


class VivertineOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Vivertine Gym.

    Options:
    - Update interval
    - Favorite class types (comma-separated names)
    - Notification service target
    - Low spots threshold
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL,
            self.config_entry.data.get(
                CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
            ),
        )
        current_favorites = self.config_entry.options.get(
            CONF_FAVORITE_CLASSES,
            self.config_entry.data.get(CONF_FAVORITE_CLASSES, ""),
        )
        current_notify = self.config_entry.options.get(
            CONF_NOTIFY_SERVICE,
            self.config_entry.data.get(CONF_NOTIFY_SERVICE, ""),
        )
        current_threshold = self.config_entry.options.get(
            CONF_LOW_SPOTS_THRESHOLD,
            self.config_entry.data.get(
                CONF_LOW_SPOTS_THRESHOLD, DEFAULT_LOW_SPOTS_THRESHOLD
            ),
        )

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=current_interval,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL
                    ),
                ),
                vol.Optional(
                    CONF_FAVORITE_CLASSES,
                    default=current_favorites,
                ): str,
                vol.Optional(
                    CONF_NOTIFY_SERVICE,
                    default=current_notify,
                ): str,
                vol.Optional(
                    CONF_LOW_SPOTS_THRESHOLD,
                    default=current_threshold,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=1, max=30),
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
        )
