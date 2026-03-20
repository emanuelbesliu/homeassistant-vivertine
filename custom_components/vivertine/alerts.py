"""Alert system for the Vivertine Gym integration.

Monitors favorite classes for changes and fires HA events + notifications:
- Class cancelled (isDeleted)
- Class time moved (startDate/endDate changed)
- Instructor changed
- Available spots below threshold

Uses a snapshot-comparison approach: each coordinator update, we compare
the current class data against the previous snapshot to detect changes.

Booking suggestions use persistent storage (homeassistant.helpers.storage.Store)
so that dismissed suggestions survive HA restarts. If the user tapped "Nu" (No)
on a suggestion, that class ID is persisted and never re-suggested. If the user
never responded, the suggestion is re-sent after restart.

Snooze ("Mă mai gândesc") uses an in-memory cooldown (default 1 hour).
After tapping, the suggestion won't re-appear until the cooldown expires,
then re-triggers on the next coordinator update cycle. After HA restart
snoozed suggestions re-trigger immediately (same as ignored).
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    CONF_FAVORITE_CLASSES,
    CONF_FAVORITE_INSTRUCTORS,
    CONF_NOTIFY_SERVICE,
    CONF_LOW_SPOTS_THRESHOLD,
    CONF_EXPIRY_REMINDER_DAYS,
    CONF_EXPIRY_DAILY_THRESHOLD,
    DEFAULT_LOW_SPOTS_THRESHOLD,
    DEFAULT_EXPIRY_REMINDER_DAYS,
    DEFAULT_EXPIRY_DAILY_THRESHOLD,
    BOOKING_WINDOW_HOURS,
    STORAGE_VERSION,
    STORAGE_KEY,
    EVENT_CLASS_CANCELLED,
    EVENT_CLASS_MOVED,
    EVENT_CLASS_INSTRUCTOR_CHANGED,
    EVENT_CLASS_LOW_SPOTS,
    EVENT_BOOKING_SUGGESTION,
    EVENT_MEMBERSHIP_EXPIRY,
    ACTION_BOOK_PREFIX,
    ACTION_DISMISS_PREFIX,
    ACTION_SNOOZE_PREFIX,
    DEFAULT_SNOOZE_COOLDOWN_SECONDS,
    DATA_CLASSES,
    DATA_BOOKINGS,
    DATA_ACTIVE_CONTRACT,
    DATA_NEXT_FAVORITE_CLASS,
    DATA_NEXT_FAVORITE_INSTRUCTOR_CLASS,
    DATA_RECOMMENDED_CLASS,
    DATA_CLASS_BUDDIES,
)

_LOGGER = logging.getLogger(__name__)


class VivertineClassAlerts:
    """Monitors favorite classes for changes and sends alerts."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the alert manager."""
        self._hass = hass
        self._entry = entry
        # Previous snapshot of classes keyed by class ID
        self._previous_classes: dict[int, dict[str, Any]] = {}
        # Track which alerts have already been sent to avoid duplicates
        # (in-memory only — cleared on restart, used for non-suggestion alerts)
        self._sent_alerts: set[str] = set()
        self._unsub: Any = None
        # Persistent storage for dismissed booking suggestions.
        # Class IDs the user explicitly dismissed ("Nu") survive restarts.
        self._store = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}"
        )
        self._dismissed_suggestions: set[int] = set()
        self._dismissed_loaded = False
        # Snooze cooldown: class_id → timestamp when snooze expires.
        # In-memory only — after HA restart, snoozed classes re-trigger
        # immediately (same as "ignored" behaviour).
        self._snoozed_suggestions: dict[int, float] = {}

    @property
    def _favorite_names(self) -> set[str]:
        """Get the set of favorite class type names (lowercased)."""
        raw = self._entry.options.get(
            CONF_FAVORITE_CLASSES,
            self._entry.data.get(CONF_FAVORITE_CLASSES, ""),
        )
        if not raw:
            return set()
        return {
            name.strip().lower()
            for name in raw.split(",")
            if name.strip()
        }

    @property
    def _favorite_instructor_names(self) -> set[str]:
        """Get the set of favorite instructor names (lowercased)."""
        raw = self._entry.options.get(
            CONF_FAVORITE_INSTRUCTORS,
            self._entry.data.get(CONF_FAVORITE_INSTRUCTORS, ""),
        )
        if not raw:
            return set()
        return {
            name.strip().lower()
            for name in raw.split(",")
            if name.strip()
        }

    @property
    def _notify_service(self) -> str | None:
        """Get the configured notification service target."""
        service = self._entry.options.get(
            CONF_NOTIFY_SERVICE,
            self._entry.data.get(CONF_NOTIFY_SERVICE, ""),
        )
        return service if service else None

    @property
    def _low_spots_threshold(self) -> int:
        """Get the low-spots alert threshold."""
        return self._entry.options.get(
            CONF_LOW_SPOTS_THRESHOLD,
            self._entry.data.get(
                CONF_LOW_SPOTS_THRESHOLD, DEFAULT_LOW_SPOTS_THRESHOLD
            ),
        )

    @property
    def _expiry_reminder_days(self) -> set[int]:
        """Get the set of days-before-expiry at which to send reminders."""
        raw = self._entry.options.get(
            CONF_EXPIRY_REMINDER_DAYS,
            self._entry.data.get(
                CONF_EXPIRY_REMINDER_DAYS, DEFAULT_EXPIRY_REMINDER_DAYS
            ),
        )
        if not raw:
            return set()
        result: set[int] = set()
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                result.add(int(part))
        return result

    @property
    def _expiry_daily_threshold(self) -> int:
        """Get the threshold below which daily expiry reminders are sent."""
        return self._entry.options.get(
            CONF_EXPIRY_DAILY_THRESHOLD,
            self._entry.data.get(
                CONF_EXPIRY_DAILY_THRESHOLD, DEFAULT_EXPIRY_DAILY_THRESHOLD
            ),
        )

    def register(self, coordinator: DataUpdateCoordinator) -> None:
        """Register listener on coordinator updates."""
        self._unsub = coordinator.async_add_listener(self._on_update)

    def unregister(self) -> None:
        """Unregister listener."""
        if self._unsub:
            self._unsub()
            self._unsub = None

    async def async_load_dismissed(self) -> None:
        """Load dismissed suggestion class IDs from persistent storage."""
        data = await self._store.async_load()
        if data and isinstance(data, dict):
            dismissed = data.get("dismissed", [])
            self._dismissed_suggestions = {
                int(cid) for cid in dismissed if str(cid).isdigit()
            }
            _LOGGER.debug(
                "Loaded %d dismissed suggestions from storage",
                len(self._dismissed_suggestions),
            )
        self._dismissed_loaded = True

    async def async_dismiss_suggestion(self, class_id: int) -> None:
        """Persistently dismiss a booking suggestion so it survives restarts."""
        self._dismissed_suggestions.add(class_id)
        self._sent_alerts.add(f"suggest_{class_id}")
        await self._store.async_save(
            {"dismissed": list(self._dismissed_suggestions)}
        )
        _LOGGER.debug(
            "Persisted dismissed suggestion for class %s (total: %d)",
            class_id,
            len(self._dismissed_suggestions),
        )

    def async_snooze_suggestion(self, class_id: int) -> None:
        """Snooze a booking suggestion so it re-triggers after a cooldown.

        Unlike dismiss (permanent), snooze is in-memory only and expires
        after DEFAULT_SNOOZE_COOLDOWN_SECONDS (1 hour).  After the cooldown,
        the suggestion will re-appear on the next coordinator update cycle.
        """
        import time

        until = time.monotonic() + DEFAULT_SNOOZE_COOLDOWN_SECONDS
        self._snoozed_suggestions[class_id] = until
        # Remove from _sent_alerts so the suggestion can re-trigger
        # once the cooldown expires.
        self._sent_alerts.discard(f"suggest_{class_id}")
        _LOGGER.info(
            "Snoozed suggestion for class %s — will re-trigger in %ds",
            class_id,
            DEFAULT_SNOOZE_COOLDOWN_SECONDS,
        )

    def send_test_notification(self) -> None:
        """Send a test notification to verify the alert pipeline works."""
        test_cls = {
            "id": "test",
            "class_type_name": "Test Class",
            "instructor_name": "Test Instructor",
            "startDate": datetime.now().isoformat(),
            "endDate": None,
            "clubZone": "Test Zone",
        }
        self._fire_alert(
            f"{DOMAIN}_test_notification",
            test_cls,
            "Notificare de test",
            "Sistemul de alerte Vivertine funcționează corect!",
        )

    @callback
    def _on_update(self) -> None:
        """Handle coordinator data update — check for class changes."""
        entry_data = self._hass.data.get(DOMAIN, {}).get(self._entry.entry_id)
        if not entry_data:
            return

        coordinator = entry_data.get("coordinator")
        if not coordinator or not coordinator.data:
            return

        # Check membership expiry (runs regardless of favorites config)
        self._check_membership_expiry(coordinator)

        favorites = self._favorite_names
        fav_instructors = self._favorite_instructor_names
        if not favorites and not fav_instructors:
            return

        # Use the full enriched class list (includes deleted classes
        # for cancellation detection)
        all_classes = coordinator.data.get(DATA_CLASSES, [])

        current_classes = self._build_class_snapshot(
            all_classes, favorites, fav_instructors
        )

        if self._previous_classes:
            self._detect_changes(current_classes)

        self._previous_classes = current_classes

        # Check for booking suggestions (actionable notifications)
        self._check_booking_suggestions(coordinator)

    def _build_class_snapshot(
        self,
        classes: list[dict[str, Any]],
        favorites: set[str],
        fav_instructors: set[str],
    ) -> dict[int, dict[str, Any]]:
        """Build a snapshot of monitored classes keyed by class ID.

        A class is included if its class_type_name matches a favorite class
        OR its instructor_name matches a favorite instructor.
        Only future classes are included — past classes are skipped to
        avoid stale alerts (e.g., low-spots on classes already held).
        """
        now = datetime.now()
        snapshot = {}
        for cls in classes:
            # Skip classes that have already started
            start_str = cls.get("startDate")
            if start_str:
                try:
                    start_dt = datetime.fromisoformat(
                        start_str.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                    if start_dt <= now:
                        continue
                except (ValueError, TypeError):
                    pass  # keep class if we can't parse the date

            class_name = (cls.get("class_type_name") or "").lower()
            instructor = (cls.get("instructor_name") or "").lower()
            is_fav_class = class_name in favorites if favorites else False
            is_fav_instructor = (
                instructor in fav_instructors if fav_instructors else False
            )
            if not is_fav_class and not is_fav_instructor:
                continue
            cls_id = cls.get("id")
            if cls_id is None:
                continue
            snapshot[cls_id] = {
                "id": cls_id,
                "class_type_name": cls.get("class_type_name", "Unknown"),
                "instructor_name": cls.get("instructor_name", "N/A"),
                "instructorId": cls.get("instructorId"),
                "startDate": cls.get("startDate"),
                "endDate": cls.get("endDate"),
                "isDeleted": cls.get("isDeleted", False),
                "attendeesCount": cls.get("attendeesCount", 0),
                "attendeesLimit": cls.get("attendeesLimit", 0),
                "available_spots": cls.get("available_spots"),
                "clubZone": cls.get("clubZone"),
            }
        return snapshot

    def _detect_changes(
        self,
        current: dict[int, dict[str, Any]],
    ) -> None:
        """Compare current vs previous snapshot and fire alerts."""
        threshold = self._low_spots_threshold
        now = datetime.now()

        for cls_id, prev_cls in self._previous_classes.items():
            curr_cls = current.get(cls_id)

            if curr_cls is None:
                # Class disappeared from snapshot — could be cancelled OR
                # simply moved to the past (already held). Only alert if
                # the class was still in the future at last check.
                prev_start_str = prev_cls.get("startDate")
                if prev_start_str:
                    try:
                        prev_start = datetime.fromisoformat(
                            prev_start_str.replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                        if prev_start <= now:
                            # Class already started — not a cancellation
                            continue
                    except (ValueError, TypeError):
                        pass

                alert_key = f"cancelled_{cls_id}"
                if alert_key not in self._sent_alerts:
                    self._sent_alerts.add(alert_key)
                    self._fire_alert(
                        EVENT_CLASS_CANCELLED,
                        prev_cls,
                        "Clasă anulată",
                        (
                            f"Clasa {prev_cls['class_type_name']} de "
                            f"{self._format_datetime(prev_cls.get('startDate'))} "
                            f"cu {prev_cls['instructor_name']} a fost anulată."
                        ),
                    )
                continue

            # Check cancellation (isDeleted changed to True)
            if curr_cls.get("isDeleted") and not prev_cls.get("isDeleted"):
                alert_key = f"cancelled_{cls_id}"
                if alert_key not in self._sent_alerts:
                    self._sent_alerts.add(alert_key)
                    self._fire_alert(
                        EVENT_CLASS_CANCELLED,
                        curr_cls,
                        "Clasă anulată",
                        (
                            f"Clasa {curr_cls['class_type_name']} de "
                            f"{self._format_datetime(curr_cls.get('startDate'))} "
                            f"cu {curr_cls['instructor_name']} a fost anulată."
                        ),
                    )

            # Check time change
            if (
                curr_cls.get("startDate") != prev_cls.get("startDate")
                or curr_cls.get("endDate") != prev_cls.get("endDate")
            ):
                if not curr_cls.get("isDeleted"):
                    alert_key = (
                        f"moved_{cls_id}_{curr_cls.get('startDate')}"
                    )
                    if alert_key not in self._sent_alerts:
                        self._sent_alerts.add(alert_key)
                        self._fire_alert(
                            EVENT_CLASS_MOVED,
                            curr_cls,
                            "Clasă reprogramată",
                            (
                                f"Clasa {curr_cls['class_type_name']} a fost "
                                f"mutată de la "
                                f"{self._format_datetime(prev_cls.get('startDate'))} "
                                f"la {self._format_datetime(curr_cls.get('startDate'))}."
                            ),
                            extra={
                                "previous_start": prev_cls.get("startDate"),
                                "previous_end": prev_cls.get("endDate"),
                            },
                        )

            # Check instructor change
            if (
                curr_cls.get("instructorId") != prev_cls.get("instructorId")
                and not curr_cls.get("isDeleted")
            ):
                alert_key = (
                    f"instructor_{cls_id}_{curr_cls.get('instructorId')}"
                )
                if alert_key not in self._sent_alerts:
                    self._sent_alerts.add(alert_key)
                    self._fire_alert(
                        EVENT_CLASS_INSTRUCTOR_CHANGED,
                        curr_cls,
                        "Instructor schimbat",
                        (
                            f"Clasa {curr_cls['class_type_name']} de "
                            f"{self._format_datetime(curr_cls.get('startDate'))} "
                            f"— instructor schimbat de la "
                            f"{prev_cls['instructor_name']} la "
                            f"{curr_cls['instructor_name']}."
                        ),
                        extra={
                            "previous_instructor": prev_cls.get(
                                "instructor_name"
                            ),
                        },
                    )

        # Check low spots on ALL current favorite classes
        for cls_id, curr_cls in current.items():
            if curr_cls.get("isDeleted"):
                continue
            spots = curr_cls.get("available_spots")
            if spots is not None and spots <= threshold and spots >= 0:
                alert_key = f"low_spots_{cls_id}_{spots}"
                if alert_key not in self._sent_alerts:
                    self._sent_alerts.add(alert_key)
                    self._fire_alert(
                        EVENT_CLASS_LOW_SPOTS,
                        curr_cls,
                        "Locuri limitate",
                        (
                            f"Clasa {curr_cls['class_type_name']} de "
                            f"{self._format_datetime(curr_cls.get('startDate'))} "
                            f"cu {curr_cls['instructor_name']} — "
                            f"doar {spots} locuri rămase!"
                        ),
                        extra={"available_spots": spots},
                    )

    def _fire_alert(
        self,
        event_type: str,
        cls_data: dict[str, Any],
        title: str,
        message: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Fire an HA event and optionally send a notification."""
        event_data = {
            "entry_id": self._entry.entry_id,
            "class_id": cls_data.get("id"),
            "class_name": cls_data.get("class_type_name"),
            "instructor": cls_data.get("instructor_name"),
            "start_date": cls_data.get("startDate"),
            "end_date": cls_data.get("endDate"),
            "zone": cls_data.get("clubZone"),
            "title": title,
            "message": message,
        }
        if extra:
            event_data.update(extra)

        self._hass.bus.async_fire(event_type, event_data)
        _LOGGER.info(
            "Vivertine alert fired [%s]: %s", event_type, message
        )

        # Persistent notification
        notification_id = (
            f"vivertine_{event_type}_{cls_data.get('id', 'unknown')}"
        )
        self._hass.async_create_task(
            self._hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "message": message,
                    "title": f"Vivertine: {title}",
                    "notification_id": notification_id,
                },
            )
        )

        # Mobile notification via configured service
        notify_target = self._notify_service
        if notify_target:
            self._hass.async_create_task(
                self._send_notification(notify_target, title, message)
            )

    async def _send_notification(
        self, target: str, title: str, message: str
    ) -> None:
        """Send a mobile notification via HA notify service."""
        try:
            await self._hass.services.async_call(
                "notify",
                target,
                {"title": f"Vivertine: {title}", "message": message},
            )
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Failed to send notification via notify.%s", target
            )

    def _check_membership_expiry(
        self,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        """Check if membership expiry reminders should be sent.

        Sends notifications at configured day thresholds (e.g., 60, 30, 14, 7)
        and daily when days_left <= daily_threshold. Also notifies on day 0
        (the actual expiry day). Never sends after expiry (days_left < 0 is
        clamped to 0 by the coordinator, and day-0 is deduped).
        """
        data = coordinator.data
        if not data:
            return

        contract = data.get(DATA_ACTIVE_CONTRACT)
        if not contract:
            return

        days_left = contract.get("days_left")
        if days_left is None:
            return

        # Don't send notifications after expiry — days_left is clamped to 0
        # by the coordinator, so once we send the day-0 alert, we stop
        # (dedup key "expiry_0" prevents re-sending).
        # If there's no active contract at all, we already returned above.

        plan_name = contract.get("plan_name", "Abonament")
        end_date = contract.get("endDate", "")

        # Format end date for display
        end_display = self._format_expiry_date(end_date)

        reminder_days = self._expiry_reminder_days
        daily_threshold = self._expiry_daily_threshold

        should_notify = False

        # Check specific day thresholds (e.g., 60, 30, 14, 7)
        if days_left in reminder_days:
            should_notify = True

        # Check daily threshold (notify every day when days_left <= threshold)
        if days_left <= daily_threshold:
            should_notify = True

        # Also notify on day 0 (the actual expiry day)
        if days_left == 0:
            should_notify = True

        if not should_notify:
            return

        # Dedup: one notification per days_left value
        alert_key = f"expiry_{days_left}"
        if alert_key in self._sent_alerts:
            return
        self._sent_alerts.add(alert_key)

        # Build Romanian message
        if days_left == 0:
            title = "Abonament expirat"
            message = (
                f"Abonamentul tău \"{plan_name}\" expiră astăzi ({end_display})! "
                f"Reînnoiește-l pentru a continua să mergi la sală."
            )
        elif days_left == 1:
            title = "Abonament expiră mâine"
            message = (
                f"Abonamentul tău \"{plan_name}\" expiră mâine ({end_display}). "
                f"Mai ai doar 1 zi!"
            )
        elif days_left <= daily_threshold:
            title = f"Abonament expiră în {days_left} zile"
            message = (
                f"Abonamentul tău \"{plan_name}\" expiră pe {end_display}. "
                f"Mai ai doar {days_left} zile!"
            )
        else:
            title = f"Abonament expiră în {days_left} zile"
            message = (
                f"Abonamentul tău \"{plan_name}\" expiră pe {end_display}. "
                f"Mai ai {days_left} zile rămase."
            )

        # Fire HA event
        event_data = {
            "entry_id": self._entry.entry_id,
            "days_left": days_left,
            "plan_name": plan_name,
            "end_date": end_date,
            "title": title,
            "message": message,
        }
        self._hass.bus.async_fire(EVENT_MEMBERSHIP_EXPIRY, event_data)
        _LOGGER.info(
            "Vivertine membership expiry alert: %d days left", days_left
        )

        # Persistent notification
        notification_id = f"vivertine_expiry_{days_left}"
        self._hass.async_create_task(
            self._hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "message": message,
                    "title": f"Vivertine: {title}",
                    "notification_id": notification_id,
                },
            )
        )

        # Mobile notification
        notify_target = self._notify_service
        if notify_target:
            self._hass.async_create_task(
                self._send_notification(notify_target, title, message)
            )

    @staticmethod
    def _format_expiry_date(dt_str: str | None) -> str:
        """Format an ISO date string to DD.MM.YYYY for Romanian display."""
        if not dt_str:
            return "?"
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            return dt.strftime("%d.%m.%Y")
        except (ValueError, TypeError):
            return dt_str or "?"

    def _check_booking_suggestions(
        self,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        """Check if recommended/favorite classes should be suggested for booking.

        Deduplicates by class ID: if 2-3 recommendation types point to the
        same class, only ONE notification is sent with combined reasons.
        """
        data = coordinator.data
        if not data:
            return

        notify_target = self._notify_service
        if not notify_target:
            return

        # Gather candidate classes with their reason labels
        candidates: dict[int, dict[str, Any]] = {}

        rec = data.get(DATA_RECOMMENDED_CLASS)
        if rec and rec.get("id") is not None:
            cid = rec["id"]
            candidates.setdefault(cid, {"cls": rec, "reasons": []})
            candidates[cid]["reasons"].append("recomandată")

        fav = data.get(DATA_NEXT_FAVORITE_CLASS)
        if fav and fav.get("id") is not None:
            cid = fav["id"]
            candidates.setdefault(cid, {"cls": fav, "reasons": []})
            candidates[cid]["reasons"].append("favorită")

        fav_inst = data.get(DATA_NEXT_FAVORITE_INSTRUCTOR_CLASS)
        if fav_inst and fav_inst.get("id") is not None:
            cid = fav_inst["id"]
            candidates.setdefault(cid, {"cls": fav_inst, "reasons": []})
            candidates[cid]["reasons"].append("instructor favorit")

        if not candidates:
            return

        # Build set of actively booked class IDs
        bookings = data.get(DATA_BOOKINGS, [])
        booked_cids: set[int] = set()
        for b in bookings:
            if not b.get("isCanceled", False):
                bcid = b.get("classId")
                if bcid is not None:
                    booked_cids.add(bcid)

        # Buddies data for enrichment
        buddies_by_class = (
            data.get(DATA_CLASS_BUDDIES, {}).get("buddies_by_class", {})
        )

        now = datetime.now()
        booking_window = timedelta(hours=BOOKING_WINDOW_HOURS)

        for cls_id, info in candidates.items():
            cls = info["cls"]
            reasons = info["reasons"]

            # Skip already booked
            if cls_id in booked_cids:
                continue

            # Skip no available spots
            spots = cls.get("available_spots")
            if spots is not None and spots <= 0:
                continue

            # Skip classes outside the booking window (>24h away)
            start_str = cls.get("startDate")
            if start_str:
                try:
                    start_dt = datetime.fromisoformat(
                        start_str.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                    if start_dt > now + booking_window:
                        continue
                    if start_dt <= now:
                        continue  # already started
                except (ValueError, TypeError):
                    pass  # keep candidate if we can't parse date

            # Skip already suggested (in-memory) or persistently dismissed
            # or currently snoozed (cooldown not yet expired)
            alert_key = f"suggest_{cls_id}"
            if alert_key in self._sent_alerts:
                continue
            if cls_id in self._dismissed_suggestions:
                continue

            # Check snooze cooldown
            import time

            snooze_until = self._snoozed_suggestions.get(cls_id)
            if snooze_until is not None:
                if time.monotonic() < snooze_until:
                    continue  # still snoozed — skip for now
                # Cooldown expired — remove from snooze dict and proceed
                del self._snoozed_suggestions[cls_id]

            self._sent_alerts.add(alert_key)

            # Build message
            class_display = self._format_class_display(cls)
            reason_str = "Clasă " + " + ".join(reasons)

            lines = [class_display, reason_str]

            # Include buddies if any
            buddies = buddies_by_class.get(cls_id, [])
            if buddies:
                if len(buddies) == 1:
                    lines.append(f"{buddies[0]} participă!")
                elif len(buddies) == 2:
                    lines.append(
                        f"{buddies[0]} și {buddies[1]} participă!"
                    )
                else:
                    names = ", ".join(buddies[:-1])
                    lines.append(
                        f"{names} și {buddies[-1]} participă!"
                    )

            if spots is not None:
                lines.append(f"{spots} locuri disponibile")

            message = "\n".join(lines)
            title = "Sugestie de rezervare"

            # Fire HA event
            event_data = {
                "entry_id": self._entry.entry_id,
                "class_id": cls_id,
                "class_name": cls.get("class_type_name"),
                "instructor": cls.get("instructor_name"),
                "start_date": cls.get("startDate"),
                "reasons": reasons,
                "buddies_going": buddies,
                "available_spots": spots,
                "title": title,
                "message": message,
            }
            self._hass.bus.async_fire(EVENT_BOOKING_SUGGESTION, event_data)
            _LOGGER.info(
                "Vivertine booking suggestion [%s]: %s",
                cls_id,
                reason_str,
            )

            # Persistent notification
            notification_id = f"vivertine_suggest_{cls_id}"
            self._hass.async_create_task(
                self._hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "message": message,
                        "title": f"Vivertine: {title}",
                        "notification_id": notification_id,
                    },
                )
            )

            # Actionable mobile notification
            actions = [
                {
                    "action": f"{ACTION_BOOK_PREFIX}{cls_id}",
                    "title": "Da, rezerva!",
                },
                {
                    "action": f"{ACTION_SNOOZE_PREFIX}{cls_id}",
                    "title": "Ma mai gandesc",
                },
                {
                    "action": f"{ACTION_DISMISS_PREFIX}{cls_id}",
                    "title": "Nu",
                },
            ]
            tag = f"vivertine_suggest_{cls_id}"
            self._hass.async_create_task(
                self._send_actionable_notification(
                    notify_target, title, message, actions, tag
                )
            )

    async def _send_actionable_notification(
        self,
        target: str,
        title: str,
        message: str,
        actions: list[dict[str, str]],
        tag: str,
    ) -> None:
        """Send an actionable mobile notification with buttons."""
        try:
            await self._hass.services.async_call(
                "notify",
                target,
                {
                    "title": f"Vivertine: {title}",
                    "message": message,
                    "data": {
                        "actions": actions,
                        "tag": tag,
                    },
                },
            )
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Failed to send actionable notification via notify.%s",
                target,
            )

    @staticmethod
    def _format_class_display(cls: dict[str, Any]) -> str:
        """Format a class into a display string for notifications.

        Format: "ClassName — Instructor @ Mâine 18:00"
        """
        name = cls.get("class_type_name", "Unknown")
        instructor = cls.get("instructor_name", "")

        if instructor and instructor != "N/A":
            base = f"{name} — {instructor}"
        else:
            base = name

        start_str = cls.get("startDate")
        if not start_str:
            return base

        try:
            start_dt = datetime.fromisoformat(
                start_str.replace("Z", "+00:00")
            ).replace(tzinfo=None)
        except (ValueError, TypeError):
            return base

        now = datetime.now()
        today = now.date()
        class_date = start_dt.date()
        time_str = start_dt.strftime("%H:%M")

        days_ro = {
            0: "Luni",
            1: "Marți",
            2: "Miercuri",
            3: "Joi",
            4: "Vineri",
            5: "Sâmbătă",
            6: "Duminică",
        }

        if class_date == today:
            return f"{base} @ {time_str}"
        elif class_date == today + timedelta(days=1):
            return f"{base} @ Mâine {time_str}"
        else:
            day_name = days_ro.get(
                class_date.weekday(), class_date.strftime("%d/%m")
            )
            return f"{base} @ {day_name} {time_str}"

    @staticmethod
    def _format_datetime(dt_str: str | None) -> str:
        """Format an ISO datetime string to a human-readable Romanian format."""
        if not dt_str:
            return "?"
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            dt = dt.replace(tzinfo=None)
            days_ro = {
                0: "Luni",
                1: "Marți",
                2: "Miercuri",
                3: "Joi",
                4: "Vineri",
                5: "Sâmbătă",
                6: "Duminică",
            }
            day_name = days_ro.get(dt.weekday(), "")
            return f"{day_name} {dt.strftime('%d.%m %H:%M')}"
        except (ValueError, TypeError):
            return dt_str or "?"
