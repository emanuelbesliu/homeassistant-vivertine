"""The Vivertine Gym integration."""

import asyncio
import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, Event

from .api import VivertineAPI, VivertineApiError
from .alerts import VivertineClassAlerts
from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_NOTIFY_SERVICE,
    BOOKING_WINDOW_HOURS,
    DATA_CLASSES,
    SERVICE_SEND_TEST_NOTIFICATION,
    SERVICE_BOOK_CLASS,
    SERVICE_CANCEL_BOOKING,
    ACTION_BOOK_PREFIX,
    ACTION_DISMISS_PREFIX,
    ACTION_SNOOZE_PREFIX,
    DEFAULT_SNOOZE_COOLDOWN_SECONDS,
    BOOKING_RETRY_ATTEMPTS,
    BOOKING_RETRY_DELAYS,
)
from .coordinator import VivertineDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def _check_booking_window(coordinator, class_id: int) -> str | None:
    """Check if a class is within the 24h booking window.

    Returns None if bookable, or a Romanian error message if not.
    """
    if not coordinator or not coordinator.data:
        return None  # can't validate, let the API decide

    classes = coordinator.data.get(DATA_CLASSES, [])
    target_cls = None
    for cls in classes:
        if cls.get("id") == class_id:
            target_cls = cls
            break

    if target_cls is None:
        return None  # class not found in data, let the API decide

    start_str = target_cls.get("startDate")
    if not start_str:
        return None

    try:
        start_dt = datetime.fromisoformat(
            start_str.replace("Z", "+00:00")
        ).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None

    now = datetime.now()

    if start_dt <= now:
        return "Clasa a început deja."

    window = timedelta(hours=BOOKING_WINDOW_HOURS)
    if start_dt > now + window:
        hours_until = (start_dt - now).total_seconds() / 3600
        return (
            f"Rezervările se pot face cu maxim {BOOKING_WINDOW_HOURS}h "
            f"înainte de clasă. Mai sunt {hours_until:.0f}h până la clasă."
        )

    return None


def _get_class_display_name(coordinator, class_id: int) -> str:
    """Return a human-readable display name for a class, or a fallback."""
    if not coordinator or not coordinator.data:
        return f"clasa #{class_id}"

    classes = coordinator.data.get(DATA_CLASSES, [])
    for cls in classes:
        if cls.get("id") == class_id:
            name = cls.get("class_type_name", "")
            instructor = cls.get("instructor_name", "")
            start_str = cls.get("startDate")

            parts = []
            if name:
                parts.append(name)
            if instructor and instructor != "N/A":
                parts.append(f"cu {instructor}")
            if start_str:
                try:
                    start_dt = datetime.fromisoformat(
                        start_str.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                    parts.append(f"@ {start_dt.strftime('%H:%M')}")
                except (ValueError, TypeError):
                    pass
            if parts:
                return " ".join(parts)
            break

    return f"clasa #{class_id}"


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

    # Load dismissed booking suggestions from persistent storage
    await alerts.async_load_dismissed()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "api": api,
        "alerts": alerts,
    }

    # Register alerts listener after data is stored
    alerts.register(coordinator)

    # Register listener for actionable notification responses (booking confirmations)
    async def _handle_notification_action(event: Event) -> None:
        """Handle mobile_app_notification_action events for booking suggestions."""
        action = event.data.get("action", "")

        # Skip events not meant for this integration
        if not action.startswith("VIVERTINE_"):
            return

        _LOGGER.debug(
            "Received mobile_app_notification_action: action=%s, "
            "full_event_data=%s",
            action,
            event.data,
        )

        try:
            await _process_notification_action(action)
        except Exception:  # noqa: BLE001
            _LOGGER.exception(
                "Unexpected error handling notification action: %s", action
            )

    async def _process_notification_action(action: str) -> None:
        """Process a Vivertine notification action (book/snooze/dismiss)."""
        if action.startswith(ACTION_BOOK_PREFIX):
            class_id_str = action[len(ACTION_BOOK_PREFIX):]
            try:
                class_id = int(class_id_str)
            except (ValueError, TypeError):
                _LOGGER.warning(
                    "Invalid class_id in notification action: %s", action
                )
                return

            _LOGGER.info("Booking class %s from notification action", class_id)
            # Validate 24h booking window
            window_error = _check_booking_window(coordinator, class_id)
            if window_error:
                _LOGGER.warning(
                    "Cannot book class %s from notification: %s",
                    class_id,
                    window_error,
                )
                notify_target = entry.options.get(
                    CONF_NOTIFY_SERVICE,
                    entry.data.get(CONF_NOTIFY_SERVICE, ""),
                )
                if notify_target:
                    await hass.services.async_call(
                        "notify",
                        notify_target,
                        {
                            "title": "Vivertine: Rezervare indisponibilă",
                            "message": window_error,
                        },
                    )
                return

            # Attempt booking with retry + backoff
            last_error: VivertineApiError | None = None
            for attempt in range(BOOKING_RETRY_ATTEMPTS):
                try:
                    await hass.async_add_executor_job(
                        api.book_class, class_id
                    )
                    _LOGGER.info(
                        "Successfully booked class %s (attempt %d)",
                        class_id,
                        attempt + 1,
                    )
                    last_error = None
                    break
                except VivertineApiError as err:
                    last_error = err
                    _LOGGER.warning(
                        "Booking attempt %d/%d for class %s failed: %s",
                        attempt + 1,
                        BOOKING_RETRY_ATTEMPTS,
                        class_id,
                        err,
                    )
                    if attempt < BOOKING_RETRY_ATTEMPTS - 1:
                        delay = BOOKING_RETRY_DELAYS[attempt]
                        _LOGGER.info(
                            "Retrying booking for class %s in %ds",
                            class_id,
                            delay,
                        )
                        await asyncio.sleep(delay)

            if last_error is not None:
                _LOGGER.error(
                    "Failed to book class %s after %d attempts: %s",
                    class_id,
                    BOOKING_RETRY_ATTEMPTS,
                    last_error,
                )
                notify_target = entry.options.get(
                    CONF_NOTIFY_SERVICE,
                    entry.data.get(CONF_NOTIFY_SERVICE, ""),
                )
                if notify_target:
                    await hass.services.async_call(
                        "notify",
                        notify_target,
                        {
                            "title": "Vivertine: Eroare rezervare",
                            "message": (
                                f"Nu am putut rezerva clasa după "
                                f"{BOOKING_RETRY_ATTEMPTS} încercări: "
                                f"{last_error}"
                            ),
                        },
                    )
                return

            # Trigger coordinator refresh
            await coordinator.async_request_refresh()

            # Send confirmation notification
            notify_target = entry.options.get(
                CONF_NOTIFY_SERVICE,
                entry.data.get(CONF_NOTIFY_SERVICE, ""),
            )
            if notify_target:
                display = _get_class_display_name(coordinator, class_id)
                await hass.services.async_call(
                    "notify",
                    notify_target,
                    {
                        "title": "Vivertine: Rezervare confirmată!",
                        "message": f"Ai rezervat {display}.",
                        "data": {
                            "tag": f"vivertine_suggest_{class_id}",
                        },
                    },
                )

        elif action.startswith(ACTION_DISMISS_PREFIX):
            class_id_str = action[len(ACTION_DISMISS_PREFIX):]
            _LOGGER.debug(
                "User dismissed booking suggestion for class %s",
                class_id_str,
            )
            # Persist the dismissal so it survives HA restarts
            try:
                dismissed_id = int(class_id_str)
            except (ValueError, TypeError):
                _LOGGER.warning(
                    "Invalid class_id in dismiss action: %s", action
                )
                return
            await alerts.async_dismiss_suggestion(dismissed_id)

            # Send confirmation notification
            notify_target = entry.options.get(
                CONF_NOTIFY_SERVICE,
                entry.data.get(CONF_NOTIFY_SERVICE, ""),
            )
            if notify_target:
                display = _get_class_display_name(coordinator, dismissed_id)
                await hass.services.async_call(
                    "notify",
                    notify_target,
                    {
                        "title": "Vivertine: Sugestie respinsă",
                        "message": (
                            f"Ai respins sugestia pentru {display}. "
                            "Nu vei mai primi această sugestie."
                        ),
                        "data": {
                            "tag": f"vivertine_suggest_{dismissed_id}",
                        },
                    },
                )

        elif action.startswith(ACTION_SNOOZE_PREFIX):
            class_id_str = action[len(ACTION_SNOOZE_PREFIX):]
            _LOGGER.info(
                "User snoozed booking suggestion for class %s",
                class_id_str,
            )
            try:
                snoozed_id = int(class_id_str)
            except (ValueError, TypeError):
                _LOGGER.warning(
                    "Invalid class_id in snooze action: %s", action
                )
                return
            alerts.async_snooze_suggestion(snoozed_id)

            # Send confirmation notification
            notify_target = entry.options.get(
                CONF_NOTIFY_SERVICE,
                entry.data.get(CONF_NOTIFY_SERVICE, ""),
            )
            if notify_target:
                display = _get_class_display_name(coordinator, snoozed_id)
                snooze_minutes = DEFAULT_SNOOZE_COOLDOWN_SECONDS // 60
                await hass.services.async_call(
                    "notify",
                    notify_target,
                    {
                        "title": "Vivertine: Sugestie amânată",
                        "message": (
                            f"Ai amânat sugestia pentru {display}. "
                            f"Vei primi din nou sugestia peste "
                            f"{snooze_minutes} minute."
                        ),
                        "data": {
                            "tag": f"vivertine_suggest_{snoozed_id}",
                        },
                    },
                )

        else:
            _LOGGER.warning(
                "Unknown Vivertine notification action: %s", action
            )

    unsub_notification_action = hass.bus.async_listen(
        "mobile_app_notification_action", _handle_notification_action
    )
    hass.data[DOMAIN][entry.entry_id][
        "unsub_notification_action"
    ] = unsub_notification_action

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
                    # Validate 24h booking window
                    window_error = _check_booking_window(coord, class_id)
                    if window_error:
                        _LOGGER.warning(
                            "Cannot book class %s: %s",
                            class_id,
                            window_error,
                        )
                        raise VivertineApiError(window_error)

                    # Attempt booking with retry + backoff
                    last_error: VivertineApiError | None = None
                    for attempt in range(BOOKING_RETRY_ATTEMPTS):
                        try:
                            result = await hass.async_add_executor_job(
                                api_inst.book_class, class_id
                            )
                            _LOGGER.info(
                                "Booked class %s (attempt %d): %s",
                                class_id,
                                attempt + 1,
                                result,
                            )
                            last_error = None
                            break
                        except VivertineApiError as err:
                            last_error = err
                            _LOGGER.warning(
                                "Service booking attempt %d/%d for "
                                "class %s failed: %s",
                                attempt + 1,
                                BOOKING_RETRY_ATTEMPTS,
                                class_id,
                                err,
                            )
                            if attempt < BOOKING_RETRY_ATTEMPTS - 1:
                                delay = BOOKING_RETRY_DELAYS[attempt]
                                _LOGGER.info(
                                    "Retrying service booking for "
                                    "class %s in %ds",
                                    class_id,
                                    delay,
                                )
                                await asyncio.sleep(delay)

                    if last_error is not None:
                        _LOGGER.error(
                            "Failed to book class %s after %d "
                            "attempts: %s",
                            class_id,
                            BOOKING_RETRY_ATTEMPTS,
                            last_error,
                        )
                        raise last_error

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
        unsub_action = data.get("unsub_notification_action")
        if unsub_action:
            unsub_action()
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
