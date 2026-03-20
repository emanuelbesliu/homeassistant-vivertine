"""Data update coordinator for the Vivertine Gym integration.

Fetches all data from the PerfectGym API and enriches classes
with instructor names and class type names (joining by ID).
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import VivertineAPI, VivertineApiError, VivertineAuthError
from .const import (
    DOMAIN,
    DEFAULT_UPDATE_INTERVAL,
    CONF_UPDATE_INTERVAL,
    CONF_FAVORITE_CLASSES,
    CONF_FAVORITE_INSTRUCTORS,
    CONF_BUSYNESS_WINDOW_HOURS,
    DEFAULT_BUSYNESS_WINDOW_HOURS,
    BUSYNESS_THRESHOLD_LOW,
    BUSYNESS_THRESHOLD_HIGH,
    BUSYNESS_LABEL_FREE,
    BUSYNESS_LABEL_MODERATE,
    BUSYNESS_LABEL_BUSY,
    CONTRACT_STATUS_CURRENT,
    DATA_ACCOUNT,
    DATA_CONTRACTS,
    DATA_ACTIVE_CONTRACT,
    DATA_PAYMENT_PLANS,
    DATA_CLASSES,
    DATA_CLASSES_TYPES,
    DATA_INSTRUCTORS,
    DATA_CLASSES_VISITS,
    DATA_BOOKINGS,
    DATA_TIMELINE,
    DATA_CLUB,
    DATA_OPENING_HOURS,
    DATA_UPCOMING_CLASSES,
    DATA_TODAYS_CLASSES,
    DATA_NEXT_CLASS,
    DATA_NEXT_FAVORITE_CLASS,
    DATA_NEXT_FAVORITE_INSTRUCTOR_CLASS,
    DATA_RECOMMENDED_CLASS,
    DATA_WEEKLY_VISITS,
    DATA_MONTHLY_VISITS,
    DATA_NOTIFICATIONS,
    DATA_CLASS_BUDDIES,
    DATA_GYM_BUSYNESS,
    VIVERTINE_CLUB_ID,
)

_LOGGER = logging.getLogger(__name__)


class VivertineDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to fetch and enrich data from PerfectGym API."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: VivertineAPI,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.api = api
        self.entry = entry

        update_interval = entry.options.get(
            CONF_UPDATE_INTERVAL,
            entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )

        # Cached reference data (rarely changes)
        self._instructors_map: dict[int, str] = {}
        self._class_types_map: dict[int, dict[str, Any]] = {}
        self._payment_plans_map: dict[int, dict[str, Any]] = {}
        self._club_info: dict[str, Any] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all data from the PerfectGym API.

        Returns enriched data with instructor/class names joined.

        Raises:
            UpdateFailed: If the API request fails.
        """
        try:
            data = await self.hass.async_add_executor_job(self._fetch_all)
        except VivertineAuthError as err:
            raise UpdateFailed(
                f"Authentication error: {err}"
            ) from err
        except VivertineApiError as err:
            raise UpdateFailed(
                f"Error fetching Vivertine data: {err}"
            ) from err

        if not data:
            raise UpdateFailed("Vivertine API returned empty data")

        _LOGGER.debug("Vivertine data updated successfully")
        return data

    def _fetch_all(self) -> dict[str, Any]:
        """Fetch all data synchronously and enrich it.

        This runs in the executor thread.
        """
        # -- Reference data (fetch every time, they're small) --
        instructors = self.api.get_instructors()
        class_types = self.api.get_classes_types()
        payment_plans = self.api.get_payment_plans()

        # Build lookup maps
        self._instructors_map = self._build_instructor_map(instructors)
        self._class_types_map = self._build_class_types_map(class_types)
        self._payment_plans_map = self._build_payment_plans_map(payment_plans)

        # -- User data --
        account = self.api.get_account()
        contracts = self.api.get_contracts()
        bookings = self.api.get_bookings()
        classes_visits = self.api.get_classes_visits()
        timeline = self.api.get_timeline()

        # -- Schedule: fetch current week + next week --
        now = datetime.now()
        start_date = now.strftime("%Y-%m-%d")
        end_date = (now + timedelta(days=14)).strftime("%Y-%m-%d")
        classes = self.api.get_classes(
            start_date=start_date, end_date=end_date
        )

        # -- Club info (once per cycle, lightweight) --
        if not self._club_info:
            clubs = self.api.get_clubs()
            for club in clubs:
                if club.get("id") == VIVERTINE_CLUB_ID:
                    self._club_info = club
                    break

        opening_hours = self.api.get_opening_hours()

        # -- Gym notifications --
        notifications: list[dict[str, Any]] = []
        try:
            raw_notifications = self.api.get_notifications()
            # Filter deleted and sort by sentDate descending
            notifications = sorted(
                [n for n in raw_notifications if not n.get("isDeleted")],
                key=lambda n: n.get("sentDate", ""),
                reverse=True,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to fetch notifications, continuing")

        # -- Class attendees (Who's In) --
        who_is_in: list[dict[str, Any]] = []
        try:
            who_is_in = self.api.get_who_is_in()
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to fetch WhoIsIn data, continuing")

        # -- Enrich data --
        enriched_classes = self._enrich_classes(classes)
        active_contract = self._find_active_contract(contracts)
        enriched_contract = self._enrich_contract(active_contract)

        # -- Compute derived data --
        upcoming = self._get_upcoming_classes(enriched_classes)
        todays = self._get_todays_classes(enriched_classes)
        next_class = upcoming[0] if upcoming else None

        # Next favorite class (filtered by favorite class type names)
        next_favorite_class = self._get_next_favorite_class(upcoming)

        # Next favorite instructor class (filtered by favorite instructor names)
        next_fav_instructor_class = self._get_next_favorite_instructor_class(
            upcoming
        )

        # Recommended class based on attendance history
        recommended_class = self._compute_recommended_class(
            upcoming, classes_visits
        )

        weekly_visits = self._count_visits_in_range(
            timeline, now - timedelta(days=7), now
        )
        monthly_visits = self._count_visits_in_range(
            timeline, now - timedelta(days=30), now
        )

        # -- Class buddies (who's going + buddy detection) --
        class_buddies = self._build_class_buddies(
            who_is_in, bookings, classes_visits, account
        )

        # -- Gym busyness (proxy from class attendees) --
        gym_busyness = self._compute_gym_busyness(enriched_classes)

        return {
            DATA_ACCOUNT: account,
            DATA_CONTRACTS: contracts,
            DATA_ACTIVE_CONTRACT: enriched_contract,
            DATA_PAYMENT_PLANS: payment_plans,
            DATA_CLASSES: enriched_classes,
            DATA_CLASSES_TYPES: class_types,
            DATA_INSTRUCTORS: instructors,
            DATA_CLASSES_VISITS: classes_visits,
            DATA_BOOKINGS: bookings,
            DATA_TIMELINE: timeline,
            DATA_CLUB: self._club_info,
            DATA_OPENING_HOURS: opening_hours,
            DATA_UPCOMING_CLASSES: upcoming,
            DATA_TODAYS_CLASSES: todays,
            DATA_NEXT_CLASS: next_class,
            DATA_NEXT_FAVORITE_CLASS: next_favorite_class,
            DATA_NEXT_FAVORITE_INSTRUCTOR_CLASS: next_fav_instructor_class,
            DATA_RECOMMENDED_CLASS: recommended_class,
            DATA_WEEKLY_VISITS: weekly_visits,
            DATA_MONTHLY_VISITS: monthly_visits,
            DATA_NOTIFICATIONS: notifications,
            DATA_CLASS_BUDDIES: class_buddies,
            DATA_GYM_BUSYNESS: gym_busyness,
        }

    # ------------------------------------------------------------------
    # Lookup map builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_instructor_map(
        instructors: list[dict[str, Any]],
    ) -> dict[int, str]:
        """Build instructor ID -> display name map."""
        result = {}
        for inst in instructors:
            inst_id = inst.get("id")
            if inst_id is None:
                continue
            # Prefer displayName, fall back to firstName + lastName
            name = inst.get("displayName")
            if not name:
                first = inst.get("firstName", "")
                last = inst.get("lastName", "")
                name = f"{first} {last}".strip()
            if name:
                result[inst_id] = name
        return result

    @staticmethod
    def _build_class_types_map(
        class_types: list[dict[str, Any]],
    ) -> dict[int, dict[str, Any]]:
        """Build class type ID -> {name, description, photoUrl} map."""
        result = {}
        for ct in class_types:
            ct_id = ct.get("id")
            if ct_id is None:
                continue
            result[ct_id] = {
                "name": ct.get("name", "Unknown"),
                "description": ct.get("description", ""),
                "photoUrl": ct.get("photoUrl"),
            }
        return result

    @staticmethod
    def _build_payment_plans_map(
        plans: list[dict[str, Any]],
    ) -> dict[int, dict[str, Any]]:
        """Build payment plan ID -> plan details map."""
        result = {}
        for plan in plans:
            plan_id = plan.get("id")
            if plan_id is None:
                continue
            result[plan_id] = {
                "name": plan.get("name", "Unknown"),
                "price": plan.get("price"),
                "period": plan.get("period"),
            }
        return result

    # ------------------------------------------------------------------
    # Data enrichment
    # ------------------------------------------------------------------

    def _enrich_classes(
        self, classes: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Enrich classes with instructor names and class type names.

        Adds: instructor_name, class_type_name, class_type_description,
              available_spots
        """
        enriched = []
        for cls in classes:
            # Skip deleted/cancelled classes from the list but keep
            # them flagged so alerts can detect cancellations
            enriched_cls = dict(cls)

            # Join instructor name
            inst_id = cls.get("instructorId")
            enriched_cls["instructor_name"] = self._instructors_map.get(
                inst_id, "N/A"
            )

            # Join class type info
            ct_id = cls.get("classTypeId")
            ct_info = self._class_types_map.get(ct_id, {})
            enriched_cls["class_type_name"] = ct_info.get("name", "Unknown")
            enriched_cls["class_type_description"] = ct_info.get(
                "description", ""
            )
            enriched_cls["class_type_photo"] = ct_info.get("photoUrl")

            # Compute available spots
            attendees = cls.get("attendeesCount", 0) or 0
            limit = cls.get("attendeesLimit", 0) or 0
            if limit > 0:
                enriched_cls["available_spots"] = max(limit - attendees, 0)
            else:
                enriched_cls["available_spots"] = None  # unlimited

            enriched.append(enriched_cls)

        return enriched

    def _find_active_contract(
        self, contracts: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Find the current/active contract."""
        for contract in contracts:
            if contract.get("status") == CONTRACT_STATUS_CURRENT:
                return contract
        return None

    def _enrich_contract(
        self, contract: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Enrich contract with payment plan name."""
        if not contract:
            return None

        enriched = dict(contract)
        plan_id = contract.get("paymentPlanId")
        if plan_id and plan_id in self._payment_plans_map:
            plan_info = self._payment_plans_map[plan_id]
            enriched["plan_name"] = plan_info["name"]
            enriched["plan_price"] = plan_info.get("price")
        else:
            enriched["plan_name"] = "Unknown Plan"

        # Calculate days remaining
        end_date_str = contract.get("endDate")
        if end_date_str:
            try:
                end_date = datetime.fromisoformat(
                    end_date_str.replace("Z", "+00:00")
                )
                days_left = (end_date.replace(tzinfo=None) - datetime.now()).days
                enriched["days_left"] = max(days_left, 0)
            except (ValueError, TypeError):
                enriched["days_left"] = None
        else:
            enriched["days_left"] = None

        return enriched

    # ------------------------------------------------------------------
    # Derived data computations
    # ------------------------------------------------------------------

    @staticmethod
    def _get_upcoming_classes(
        classes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Get upcoming classes (not deleted, in the future), sorted by start."""
        now = datetime.now()
        upcoming = []
        for cls in classes:
            if cls.get("isDeleted"):
                continue
            start_str = cls.get("startDate")
            if not start_str:
                continue
            try:
                start = datetime.fromisoformat(
                    start_str.replace("Z", "+00:00")
                ).replace(tzinfo=None)
                if start > now:
                    cls["_parsed_start"] = start
                    upcoming.append(cls)
            except (ValueError, TypeError):
                continue

        upcoming.sort(key=lambda c: c.get("_parsed_start", now))
        return upcoming

    @staticmethod
    def _get_todays_classes(
        classes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Get today's classes (not deleted), sorted by start time."""
        today = datetime.now().date()
        todays = []
        for cls in classes:
            if cls.get("isDeleted"):
                continue
            start_str = cls.get("startDate")
            if not start_str:
                continue
            try:
                start = datetime.fromisoformat(
                    start_str.replace("Z", "+00:00")
                ).replace(tzinfo=None)
                if start.date() == today:
                    cls["_parsed_start"] = start
                    todays.append(cls)
            except (ValueError, TypeError):
                continue

        todays.sort(key=lambda c: c.get("_parsed_start", datetime.now()))
        return todays

    def _get_next_favorite_class(
        self,
        upcoming: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Get the next upcoming class matching a favorite class type."""
        raw = self.entry.options.get(
            CONF_FAVORITE_CLASSES,
            self.entry.data.get(CONF_FAVORITE_CLASSES, ""),
        )
        if not raw:
            return None
        favorites = {
            name.strip().lower()
            for name in raw.split(",")
            if name.strip()
        }
        if not favorites:
            return None
        for cls in upcoming:
            class_name = (cls.get("class_type_name") or "").lower()
            if class_name in favorites:
                return cls
        return None

    def _get_next_favorite_instructor_class(
        self,
        upcoming: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Get the next upcoming class taught by a favorite instructor."""
        raw = self.entry.options.get(
            CONF_FAVORITE_INSTRUCTORS,
            self.entry.data.get(CONF_FAVORITE_INSTRUCTORS, ""),
        )
        if not raw:
            return None
        favorites = {
            name.strip().lower()
            for name in raw.split(",")
            if name.strip()
        }
        if not favorites:
            return None
        for cls in upcoming:
            instructor = (cls.get("instructor_name") or "").lower()
            if instructor in favorites:
                return cls
        return None

    @staticmethod
    def _compute_recommended_class(
        upcoming: list[dict[str, Any]],
        classes_visits: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Recommend the best upcoming class based on attendance history.

        Scoring algorithm:
        - Count how many times the user attended each class type
          (by className from visits history).
        - Count attendance per class type + instructor combo for bonus.
        - Score each upcoming class:
          class_type_count * 2 + combo_count
        - Return the highest-scoring upcoming class.
        - If tied, prefer the sooner class (upcoming is already sorted).

        Returns None if there are no upcoming classes or no visit history.
        """
        if not upcoming or not classes_visits:
            return None

        # Count attendance per class type name (case-insensitive)
        type_counts: dict[str, int] = {}
        combo_counts: dict[str, int] = {}
        for visit in classes_visits:
            class_name = (visit.get("className") or "").strip().lower()
            if not class_name:
                continue
            type_counts[class_name] = type_counts.get(class_name, 0) + 1

            # Build combo key from visit — visits don't have instructor
            # names directly, so we can only count class type frequency.
            # Combo bonus comes from matching upcoming class instructor
            # with the most-attended class type.

        # Also count type+instructor combos from the visit history
        # Note: classes_visits has 'className' but not instructor info,
        # so the combo bonus uses upcoming class data where we have both.
        # We'll score purely on type frequency, with a small recency bonus
        # for classes happening sooner (inherent from sorted order).

        best_cls = None
        best_score = -1

        for cls in upcoming:
            cls_type = (cls.get("class_type_name") or "").strip().lower()
            if not cls_type:
                continue

            # Base score: how many times user attended this class type
            type_score = type_counts.get(cls_type, 0)

            # Total score (weight type attendance x2)
            score = type_score * 2

            if score > best_score:
                best_score = score
                best_cls = cls

        if best_cls and best_score > 0:
            # Attach recommendation metadata for sensor attributes
            cls_type = (
                best_cls.get("class_type_name") or ""
            ).strip().lower()
            best_cls = dict(best_cls)  # shallow copy to avoid mutation
            best_cls["_recommendation_score"] = best_score
            best_cls["_type_attendance_count"] = type_counts.get(cls_type, 0)
            return best_cls

        return None

    # ------------------------------------------------------------------
    # Class buddies (Who's Going + buddy detection)
    # ------------------------------------------------------------------

    @staticmethod
    def _format_attendee_name(entry: dict[str, Any]) -> str:
        """Format an attendee name as 'FirstName L.' for privacy.

        Uses firstName + first letter of lastName with a period.
        Falls back to nickName if both are empty.
        """
        first = (entry.get("firstName") or "").strip()
        last = (entry.get("lastName") or "").strip()
        nick = (entry.get("nickName") or "").strip()

        if first and last:
            return f"{first} {last[0]}."
        if first:
            return first
        if nick:
            return nick
        return "Unknown"

    @staticmethod
    def _build_class_buddies(
        who_is_in: list[dict[str, Any]],
        bookings: list[dict[str, Any]],
        classes_visits: list[dict[str, Any]],
        account: dict[str, Any],
    ) -> dict[str, Any]:
        """Build class buddies data from WhoIsIn attendee lists.

        Returns a dict with:
            - "next_booked_class_id": the class ID of the user's next booking
            - "next_booked_attendee_count": count for that class
            - "by_class": dict keyed by classId -> list of attendee dicts
              Each attendee: {"name": str, "is_standby": bool, "is_buddy": bool}
              Only contains entries for actively booked classes.
            - "buddies_by_class": dict keyed by classId -> list of buddy
              name strings. Covers ALL classes in WhoIsIn, not just
              booked ones. Used by sensors that may point to unbooked
              classes (recommended, favorite class, favorite instructor).

        Buddy detection: A person is a 'buddy' if they appeared in at
        least one past class that the user also booked. We use the
        bookings endpoint (which has classId for both past and future
        bookings) to find the user's past class IDs, then cross-reference
        with WhoIsIn entries for those classes.

        Note: classes_visits does NOT have classId, only className —
        so we use bookings as the source of past class IDs instead.
        """
        if not who_is_in:
            return {
                "next_booked_class_id": None,
                "next_booked_attendee_count": 0,
                "by_class": {},
                "buddies_by_class": {},
            }

        # 1. Separate bookings into all class IDs (for buddy detection)
        #    and active (non-canceled) class IDs (for attendee display)
        all_booked_class_ids: set[int] = set()
        active_booked_class_ids: set[int] = set()
        for b in bookings:
            cid = b.get("classId")
            if cid is None:
                continue
            all_booked_class_ids.add(cid)
            if not b.get("isCanceled", False):
                active_booked_class_ids.add(cid)

        if not active_booked_class_ids:
            return {
                "next_booked_class_id": None,
                "next_booked_attendee_count": 0,
                "by_class": {},
                "buddies_by_class": {},
            }

        # 2. Get user's own name to exclude from attendee lists
        user_first = (account.get("firstName") or "").strip().lower()
        user_last = (account.get("lastName") or "").strip().lower()

        # 3. Index all WhoIsIn entries by classId for fast lookup
        who_by_class: dict[int, list[dict[str, Any]]] = {}
        for entry in who_is_in:
            cid = entry.get("classId")
            if cid is None:
                continue
            who_by_class.setdefault(cid, []).append(entry)

        # 4. Build person-to-classIds index from WhoIsIn for O(1) buddy lookups
        #    Key: (firstName_lower, lastName_lower), Value: set of classIds
        #    A person is a "buddy" if they appear in at least one OTHER
        #    booked class besides the current one being viewed.
        person_class_ids: dict[tuple[str, str], set[int]] = {}
        for cid in all_booked_class_ids:
            for entry in who_by_class.get(cid, []):
                if entry.get("isCanceled") or entry.get("isDeleted"):
                    continue
                e_first = (entry.get("firstName") or "").strip().lower()
                e_last = (entry.get("lastName") or "").strip().lower()
                if e_first == user_first and e_last == user_last:
                    continue
                person_class_ids.setdefault(
                    (e_first, e_last), set()
                ).add(cid)

        # 5. Build attendee lists for each active booked class
        by_class: dict[int, list[dict[str, Any]]] = {}
        for booked_cid in active_booked_class_ids:
            class_attendees = who_by_class.get(booked_cid, [])
            attendees = []
            for entry in class_attendees:
                if entry.get("isCanceled") or entry.get("isDeleted"):
                    continue
                e_first = (entry.get("firstName") or "").strip().lower()
                e_last = (entry.get("lastName") or "").strip().lower()
                if e_first == user_first and e_last == user_last:
                    continue
                name = (
                    VivertineDataUpdateCoordinator._format_attendee_name(
                        entry
                    )
                )
                # Buddy = appears in at least one OTHER user-booked class
                their_classes = person_class_ids.get(
                    (e_first, e_last), set()
                )
                is_buddy = bool(their_classes - {booked_cid})

                attendees.append(
                    {
                        "name": name,
                        "is_standby": bool(entry.get("isStandby", False)),
                        "is_buddy": is_buddy,
                    }
                )
            # Sort: buddies first, then alphabetical
            attendees.sort(
                key=lambda a: (not a["is_buddy"], a["name"])
            )
            by_class[booked_cid] = attendees

        # 6. Build buddies-only lists for ALL classes in WhoIsIn.
        #    This allows sensors for non-booked classes (recommended,
        #    favorite class/instructor) to show which buddies are going.
        #    Only stores names of known buddies — lightweight.
        #    A person is a buddy if they appear in ANY user-booked class
        #    (i.e., they are in person_class_ids with at least 1 entry).
        buddy_name_set: set[str] = set()
        for key, class_set in person_class_ids.items():
            # Person appears in at least 1 user-booked class → is a buddy
            # Build their formatted name from any WhoIsIn entry
            for cid_check in class_set:
                for entry in who_by_class.get(cid_check, []):
                    e_f = (
                        entry.get("firstName") or ""
                    ).strip().lower()
                    e_l = (
                        entry.get("lastName") or ""
                    ).strip().lower()
                    if (e_f, e_l) == key:
                        buddy_name_set.add(
                            VivertineDataUpdateCoordinator
                            ._format_attendee_name(entry)
                        )
                        break
                break  # only need one entry for the name

        buddies_by_class: dict[int, list[str]] = {}
        for cid, entries in who_by_class.items():
            class_buddies: list[str] = []
            for entry in entries:
                if entry.get("isCanceled") or entry.get("isDeleted"):
                    continue
                e_first = (
                    entry.get("firstName") or ""
                ).strip().lower()
                e_last = (
                    entry.get("lastName") or ""
                ).strip().lower()
                if e_first == user_first and e_last == user_last:
                    continue
                name = (
                    VivertineDataUpdateCoordinator._format_attendee_name(
                        entry
                    )
                )
                if name in buddy_name_set:
                    class_buddies.append(name)
            if class_buddies:
                class_buddies.sort()
                buddies_by_class[cid] = class_buddies

        # 7. Determine the "next" booked class (earliest start time)
        #    The sensor layer will pick the actual "next" one based on
        #    class start times from DATA_UPCOMING_CLASSES
        next_booked_cid: int | None = None
        next_booked_count = 0

        if by_class:
            first_cid = next(iter(by_class))
            next_booked_cid = first_cid
            next_booked_count = len(by_class[first_cid])

        return {
            "next_booked_class_id": next_booked_cid,
            "next_booked_attendee_count": next_booked_count,
            "by_class": by_class,
            "buddies_by_class": buddies_by_class,
        }

    # ------------------------------------------------------------------
    # Gym busyness estimation
    # ------------------------------------------------------------------

    def _compute_gym_busyness(
        self, classes: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Estimate gym busyness from class attendees in a time window.

        Vivertine's real occupancy API returns null, so we use the sum of
        attendeesCount / attendeesLimit for classes starting within the
        configured window as a proxy for how busy the gym will be.

        Returns a dict with:
            label: str          — Liber / Moderat / Aglomerat
            total_attendees: int
            total_capacity: int
            occupancy_percent: float
            classes_count: int
            classes: list[dict] — per-class breakdown (capped at 10)
        """
        window_hours = self.entry.options.get(
            CONF_BUSYNESS_WINDOW_HOURS,
            self.entry.data.get(
                CONF_BUSYNESS_WINDOW_HOURS, DEFAULT_BUSYNESS_WINDOW_HOURS
            ),
        )

        now = datetime.now()
        window_end = now + timedelta(hours=window_hours)

        total_attendees = 0
        total_capacity = 0
        class_breakdown: list[dict[str, Any]] = []

        for cls in classes:
            if cls.get("isDeleted"):
                continue
            start_str = cls.get("startDate")
            if not start_str:
                continue
            try:
                start_dt = datetime.fromisoformat(
                    start_str.replace("Z", "+00:00")
                ).replace(tzinfo=None)
            except (ValueError, TypeError):
                continue

            # Only consider classes within the window (future only)
            if start_dt < now or start_dt > window_end:
                continue

            attendees = cls.get("attendeesCount", 0) or 0
            limit = cls.get("attendeesLimit", 0) or 0
            total_attendees += attendees
            total_capacity += limit

            class_breakdown.append(
                {
                    "class_name": cls.get("class_type_name", "Unknown"),
                    "instructor": cls.get("instructor_name", "N/A"),
                    "start": start_str,
                    "attendees": attendees,
                    "capacity": limit,
                }
            )

        # Compute occupancy percentage
        if total_capacity > 0:
            occupancy_pct = round(
                (total_attendees / total_capacity) * 100, 1
            )
        else:
            occupancy_pct = 0.0

        # Determine categorical label
        if occupancy_pct < BUSYNESS_THRESHOLD_LOW:
            label = BUSYNESS_LABEL_FREE
        elif occupancy_pct <= BUSYNESS_THRESHOLD_HIGH:
            label = BUSYNESS_LABEL_MODERATE
        else:
            label = BUSYNESS_LABEL_BUSY

        return {
            "label": label,
            "total_attendees": total_attendees,
            "total_capacity": total_capacity,
            "occupancy_percent": occupancy_pct,
            "classes_count": len(class_breakdown),
            "window_hours": window_hours,
            "classes": class_breakdown[:10],
        }

    @staticmethod
    def _count_visits_in_range(
        timeline: list[dict[str, Any]],
        start: datetime,
        end: datetime,
    ) -> int:
        """Count club visits in a date range from the timeline."""
        count = 0
        for entry in timeline:
            if entry.get("activityType") != "ClubVisit":
                continue
            date_str = entry.get("startDate") or entry.get("date")
            if not date_str:
                continue
            try:
                visit_dt = datetime.fromisoformat(
                    date_str.replace("Z", "+00:00")
                ).replace(tzinfo=None)
                if start <= visit_dt <= end:
                    count += 1
            except (ValueError, TypeError):
                continue
        return count
