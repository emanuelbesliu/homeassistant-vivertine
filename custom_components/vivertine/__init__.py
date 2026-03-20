"""The Vivertine Gym integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .api import VivertineAPI
from .alerts import VivertineClassAlerts
from .const import DOMAIN, PLATFORMS, CONF_EMAIL, CONF_PASSWORD

SERVICE_SEND_TEST_NOTIFICATION = "send_test_notification"
from .coordinator import VivertineDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Vivertine Gym from a config entry."""
    api = VivertineAPI(
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
    )

    # Authenticate before first refresh
    await hass.async_add_executor_job(api.authenticate)

    coordinator = VivertineDataUpdateCoordinator(hass, api, entry)
    await coordinator.async_config_entry_first_refresh()

    # Set up alerts for favorite class monitoring
    alerts = VivertineClassAlerts(hass, entry)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "api": api,
        "alerts": alerts,
    }

    # Register alerts listener after data is stored
    alerts.register(coordinator)

    # Register services (only once, for the first entry)
    if not hass.services.has_service(DOMAIN, SERVICE_SEND_TEST_NOTIFICATION):

        async def handle_send_test_notification(call: ServiceCall) -> None:
            """Handle the send_test_notification service call."""
            # Send via every registered entry's alerts instance
            for eid, edata in hass.data.get(DOMAIN, {}).items():
                alert_mgr = edata.get("alerts")
                if alert_mgr:
                    alert_mgr.send_test_notification()

        hass.services.async_register(
            DOMAIN,
            SERVICE_SEND_TEST_NOTIFICATION,
            handle_send_test_notification,
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Vivertine Gym config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )

    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        alerts = data.get("alerts")
        if alerts:
            alerts.unregister()
        api = data["api"]
        await hass.async_add_executor_job(api.close)

        # Remove service when last entry is unloaded
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_SEND_TEST_NOTIFICATION)

    return unload_ok


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle options update - reload the integration."""
    await hass.config_entries.async_reload(entry.entry_id)
