"""The Vivertine Gym integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .api import VivertineAPI, VivertineApiError
from .alerts import VivertineClassAlerts
from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_EMAIL,
    CONF_PASSWORD,
    SERVICE_SEND_TEST_NOTIFICATION,
    SERVICE_BOOK_CLASS,
    SERVICE_CANCEL_BOOKING,
)
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

    if not hass.services.has_service(DOMAIN, SERVICE_BOOK_CLASS):

        async def handle_book_class(call: ServiceCall) -> None:
            """Handle the book_class service call."""
            class_id = call.data["class_id"]
            # Use the first available entry's API instance
            for eid, edata in hass.data.get(DOMAIN, {}).items():
                api_inst = edata.get("api")
                coord = edata.get("coordinator")
                if api_inst:
                    try:
                        result = await hass.async_add_executor_job(
                            api_inst.book_class, class_id
                        )
                        _LOGGER.info(
                            "Booked class %s: %s", class_id, result
                        )
                    except VivertineApiError as err:
                        _LOGGER.error(
                            "Failed to book class %s: %s", class_id, err
                        )
                        raise
                    if coord:
                        await coord.async_request_refresh()
                    break

        hass.services.async_register(
            DOMAIN,
            SERVICE_BOOK_CLASS,
            handle_book_class,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_CANCEL_BOOKING):

        async def handle_cancel_booking(call: ServiceCall) -> None:
            """Handle the cancel_booking service call."""
            class_booking_id = call.data["class_booking_id"]
            for eid, edata in hass.data.get(DOMAIN, {}).items():
                api_inst = edata.get("api")
                coord = edata.get("coordinator")
                if api_inst:
                    try:
                        result = await hass.async_add_executor_job(
                            api_inst.cancel_booking, class_booking_id
                        )
                        _LOGGER.info(
                            "Cancelled booking %s: %s",
                            class_booking_id,
                            result,
                        )
                    except VivertineApiError as err:
                        _LOGGER.error(
                            "Failed to cancel booking %s: %s",
                            class_booking_id,
                            err,
                        )
                        raise
                    if coord:
                        await coord.async_request_refresh()
                    break

        hass.services.async_register(
            DOMAIN,
            SERVICE_CANCEL_BOOKING,
            handle_cancel_booking,
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

        # Remove services when last entry is unloaded
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_SEND_TEST_NOTIFICATION)
            hass.services.async_remove(DOMAIN, SERVICE_BOOK_CLASS)
            hass.services.async_remove(DOMAIN, SERVICE_CANCEL_BOOKING)

    return unload_ok


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle options update - reload the integration."""
    await hass.config_entries.async_reload(entry.entry_id)
