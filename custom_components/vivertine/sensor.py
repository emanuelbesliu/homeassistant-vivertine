"""Sensor platform for the Vivertine Gym integration."""

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SENSOR_TYPES,
    SENSOR_MEMBERSHIP_STATUS,
    SENSOR_MEMBERSHIP_EXPIRY,
    SENSOR_MEMBERSHIP_DAYS_LEFT,
    SENSOR_MEMBERSHIP_PLAN,
    SENSOR_NEXT_CLASS,
    SENSOR_TODAYS_CLASSES,
    SENSOR_WEEKLY_VISITS,
    SENSOR_MONTHLY_VISITS,
    SENSOR_TOTAL_VISITS,
    SENSOR_ACTIVE_BOOKINGS,
    DATA_ACTIVE_CONTRACT,
    DATA_ACCOUNT,
    DATA_UPCOMING_CLASSES,
    DATA_TODAYS_CLASSES,
    DATA_NEXT_CLASS,
    DATA_WEEKLY_VISITS,
    DATA_MONTHLY_VISITS,
    DATA_TIMELINE,
    DATA_BOOKINGS,
    DATA_CLASSES_VISITS,
    DATA_CLUB,
)
from .coordinator import VivertineDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vivertine sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities = []
    for sensor_key, sensor_config in SENSOR_TYPES.items():
        entities.append(
            VivertineSensor(
                coordinator=coordinator,
                entry=entry,
                sensor_key=sensor_key,
                sensor_config=sensor_config,
            )
        )

    # Add the schedule sensor (enriched class list as attributes)
    entities.append(
        VivertineScheduleSensor(coordinator=coordinator, entry=entry)
    )

    async_add_entities(entities)


class VivertineSensor(
    CoordinatorEntity[VivertineDataUpdateCoordinator], SensorEntity
):
    """Representation of a Vivertine sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VivertineDataUpdateCoordinator,
        entry: ConfigEntry,
        sensor_key: str,
        sensor_config: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_key = sensor_key
        self._sensor_config = sensor_config
        self._attr_unique_id = f"{entry.entry_id}_{sensor_key}"
        self._attr_name = sensor_config["name"]
        self._attr_icon = sensor_config["icon"]

        unit = sensor_config.get("unit")
        if unit:
            self._attr_native_unit_of_measurement = unit

        dc = sensor_config.get("device_class")
        if dc == "timestamp":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        elif dc:
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info for Vivertine Gym."""
        return {
            "identifiers": {(DOMAIN, "vivertine_gym")},
            "name": "Vivertine Gym",
            "manufacturer": "PerfectGym",
            "model": "Vivertine Iași",
            "entry_type": "service",
            "configuration_url": "https://vivertine.ro",
        }

    @property
    def native_value(self) -> Any:
        """Return the sensor value based on sensor_key."""
        if self.coordinator.data is None:
            return None

        key = self._sensor_key
        data = self.coordinator.data

        if key == SENSOR_MEMBERSHIP_STATUS:
            contract = data.get(DATA_ACTIVE_CONTRACT)
            if contract:
                return contract.get("status", "Unknown")
            return "No Active Membership"

        if key == SENSOR_MEMBERSHIP_EXPIRY:
            contract = data.get(DATA_ACTIVE_CONTRACT)
            if contract:
                end_str = contract.get("endDate")
                if end_str:
                    try:
                        return datetime.fromisoformat(
                            end_str.replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError):
                        return None
            return None

        if key == SENSOR_MEMBERSHIP_DAYS_LEFT:
            contract = data.get(DATA_ACTIVE_CONTRACT)
            if contract:
                return contract.get("days_left")
            return None

        if key == SENSOR_MEMBERSHIP_PLAN:
            contract = data.get(DATA_ACTIVE_CONTRACT)
            if contract:
                return contract.get("plan_name", "Unknown")
            return None

        if key == SENSOR_NEXT_CLASS:
            next_cls = data.get(DATA_NEXT_CLASS)
            if next_cls:
                name = next_cls.get("class_type_name", "Unknown")
                instructor = next_cls.get("instructor_name", "")
                return f"{name} ({instructor})" if instructor else name
            return "None"

        if key == SENSOR_TODAYS_CLASSES:
            todays = data.get(DATA_TODAYS_CLASSES, [])
            return len(todays)

        if key == SENSOR_WEEKLY_VISITS:
            return data.get(DATA_WEEKLY_VISITS, 0)

        if key == SENSOR_MONTHLY_VISITS:
            return data.get(DATA_MONTHLY_VISITS, 0)

        if key == SENSOR_TOTAL_VISITS:
            timeline = data.get(DATA_TIMELINE, [])
            return len(
                [e for e in timeline if e.get("activityType") == "ClubVisit"]
            )

        if key == SENSOR_ACTIVE_BOOKINGS:
            bookings = data.get(DATA_BOOKINGS, [])
            active = [
                b for b in bookings
                if not b.get("isCanceled", False)
            ]
            return len(active)

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {}
        if self.coordinator.data is None:
            return attrs

        key = self._sensor_key
        data = self.coordinator.data

        if key == SENSOR_MEMBERSHIP_STATUS:
            contract = data.get(DATA_ACTIVE_CONTRACT)
            if contract:
                attrs["plan_name"] = contract.get("plan_name")
                attrs["start_date"] = contract.get("startDate")
                attrs["end_date"] = contract.get("endDate")
                attrs["days_left"] = contract.get("days_left")
                attrs["plan_price"] = contract.get("plan_price")
            account = data.get(DATA_ACCOUNT)
            if account:
                attrs["member_name"] = (
                    f"{account.get('firstName', '')} "
                    f"{account.get('lastName', '')}"
                ).strip()
                attrs["member_email"] = account.get("email")
            club = data.get(DATA_CLUB)
            if club:
                attrs["club_name"] = club.get("name")
                attrs["club_address"] = club.get("address")

        elif key == SENSOR_NEXT_CLASS:
            next_cls = data.get(DATA_NEXT_CLASS)
            if next_cls:
                attrs["class_name"] = next_cls.get("class_type_name")
                attrs["instructor"] = next_cls.get("instructor_name")
                attrs["start_time"] = next_cls.get("startDate")
                attrs["end_time"] = next_cls.get("endDate")
                attrs["zone"] = next_cls.get("clubZone")
                attrs["available_spots"] = next_cls.get("available_spots")
                attrs["attendees"] = next_cls.get("attendeesCount")
                attrs["limit"] = next_cls.get("attendeesLimit")

        elif key == SENSOR_TODAYS_CLASSES:
            todays = data.get(DATA_TODAYS_CLASSES, [])
            schedule = []
            for cls in todays[:20]:  # limit to avoid huge attributes
                schedule.append(
                    {
                        "class": cls.get("class_type_name"),
                        "instructor": cls.get("instructor_name"),
                        "start": cls.get("startDate"),
                        "end": cls.get("endDate"),
                        "zone": cls.get("clubZone"),
                        "spots": cls.get("available_spots"),
                    }
                )
            attrs["schedule"] = schedule

        elif key == SENSOR_ACTIVE_BOOKINGS:
            bookings = data.get(DATA_BOOKINGS, [])
            active = [
                b for b in bookings if not b.get("isCanceled", False)
            ]
            booking_list = []
            for b in active[:10]:
                booking_list.append(
                    {
                        "class_id": b.get("classId"),
                        "is_standby": b.get("isStandby"),
                        "standby_position": b.get("standbyPosition"),
                    }
                )
            attrs["bookings"] = booking_list

        elif key == SENSOR_TOTAL_VISITS:
            # Last 5 visits for quick view
            visits = data.get(DATA_CLASSES_VISITS, [])
            recent = []
            for v in visits[:5]:
                recent.append(
                    {
                        "class": v.get("className"),
                        "date": v.get("startDate"),
                        "club": v.get("clubName"),
                    }
                )
            attrs["recent_visits"] = recent

        return attrs


class VivertineScheduleSensor(
    CoordinatorEntity[VivertineDataUpdateCoordinator], SensorEntity
):
    """Sensor showing the full upcoming schedule as attributes.

    State: number of upcoming classes in the next 7 days.
    Attributes: full schedule with instructor names, times, spots.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VivertineDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the schedule sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_upcoming_schedule"
        self._attr_name = "Upcoming Schedule"
        self._attr_icon = "mdi:calendar-clock"
        self._attr_native_unit_of_measurement = "classes"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info for Vivertine Gym."""
        return {
            "identifiers": {(DOMAIN, "vivertine_gym")},
            "name": "Vivertine Gym",
            "manufacturer": "PerfectGym",
            "model": "Vivertine Iași",
            "entry_type": "service",
            "configuration_url": "https://vivertine.ro",
        }

    @property
    def native_value(self) -> int | None:
        """Return count of upcoming classes."""
        if self.coordinator.data is None:
            return None
        upcoming = self.coordinator.data.get(DATA_UPCOMING_CLASSES, [])
        return len(upcoming)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the full upcoming schedule as attributes."""
        attrs = {}
        if self.coordinator.data is None:
            return attrs

        upcoming = self.coordinator.data.get(DATA_UPCOMING_CLASSES, [])

        # Group by day for readability
        by_day: dict[str, list] = {}
        for cls in upcoming[:50]:  # cap at 50 entries
            start_str = cls.get("startDate", "")
            try:
                start_dt = datetime.fromisoformat(
                    start_str.replace("Z", "+00:00")
                ).replace(tzinfo=None)
                day_key = start_dt.strftime("%Y-%m-%d")
                time_str = start_dt.strftime("%H:%M")
            except (ValueError, TypeError):
                day_key = "unknown"
                time_str = "?"

            end_str = cls.get("endDate", "")
            try:
                end_dt = datetime.fromisoformat(
                    end_str.replace("Z", "+00:00")
                ).replace(tzinfo=None)
                end_time = end_dt.strftime("%H:%M")
            except (ValueError, TypeError):
                end_time = "?"

            entry = {
                "time": f"{time_str}-{end_time}",
                "class": cls.get("class_type_name", "Unknown"),
                "instructor": cls.get("instructor_name", "N/A"),
                "zone": cls.get("clubZone", ""),
                "spots": cls.get("available_spots"),
            }

            by_day.setdefault(day_key, []).append(entry)

        attrs["schedule"] = by_day
        return attrs
