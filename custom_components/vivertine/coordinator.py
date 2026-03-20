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
