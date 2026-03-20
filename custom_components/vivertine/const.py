"""Constants for the Vivertine Gym integration."""

DOMAIN = "vivertine"
PLATFORMS = ["sensor"]

# PerfectGym API
API_BASE_URL = "https://goapi2.perfectgym.com"
API_VERSION = "v1"
WHITE_LABEL_ID = "EBCA70D9-37E3-4453-96AC-E3373389ECFB"

# API endpoints
ENDPOINT_LOGIN = f"/{API_VERSION}/Authorize/LogInWithEmail"
ENDPOINT_ACCOUNT = f"/{API_VERSION}/Accounts/Account"
ENDPOINT_CLUBS = f"/{API_VERSION}/Clubs/Clubs"
ENDPOINT_OPENING_HOURS = f"/{API_VERSION}/Clubs/OpeningHours"
ENDPOINT_CONTRACTS = f"/{API_VERSION}/RemoteAccounts/Contracts"
ENDPOINT_PAYMENT_PLANS = f"/{API_VERSION}/RemoteAccounts/PaymentPlans"
ENDPOINT_CHARGES = f"/{API_VERSION}/RemoteAccounts/ContractsCharges"
ENDPOINT_CLASSES = f"/{API_VERSION}/Classes/Classes"
ENDPOINT_CLASSES_TYPES = f"/{API_VERSION}/Classes/ClassesTypes"
ENDPOINT_CLASSES_VISITS = f"/{API_VERSION}/Classes/ClassesVisits"
ENDPOINT_BOOKINGS = f"/{API_VERSION}/Classes/Bookings"
ENDPOINT_INSTRUCTORS = f"/{API_VERSION}/Instructors/Instructors"
ENDPOINT_TIMELINE = f"/{API_VERSION}/Timeline/Timeline"
ENDPOINT_BOOK_CLASS = f"/{API_VERSION}/Classes/Book"
ENDPOINT_CANCEL_BOOKING = f"/{API_VERSION}/Classes/CancelBooking"
ENDPOINT_NOTIFICATIONS = f"/{API_VERSION}/PushNotifications/Notifications"
ENDPOINT_WHO_IS_IN = f"/{API_VERSION}/Classes/WhoIsIn"

# Configuration keys
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_FAVORITE_CLASSES = "favorite_classes"
CONF_FAVORITE_INSTRUCTORS = "favorite_instructors"
CONF_NOTIFY_SERVICE = "notify_service"
CONF_LOW_SPOTS_THRESHOLD = "low_spots_threshold"

# Defaults
DEFAULT_UPDATE_INTERVAL = 300  # 5 minutes
MIN_UPDATE_INTERVAL = 60
MAX_UPDATE_INTERVAL = 3600
DEFAULT_LOW_SPOTS_THRESHOLD = 5

# Alert events
EVENT_CLASS_CANCELLED = f"{DOMAIN}_class_cancelled"
EVENT_CLASS_MOVED = f"{DOMAIN}_class_moved"
EVENT_CLASS_INSTRUCTOR_CHANGED = f"{DOMAIN}_class_instructor_changed"
EVENT_CLASS_LOW_SPOTS = f"{DOMAIN}_class_low_spots"
EVENT_BOOKING_SUGGESTION = f"{DOMAIN}_booking_suggestion"

# Actionable notification action prefixes
ACTION_BOOK_PREFIX = "VIVERTINE_BOOK_"
ACTION_DISMISS_PREFIX = "VIVERTINE_DISMISS_"

# Data keys in coordinator.data
DATA_ACCOUNT = "account"
DATA_CONTRACTS = "contracts"
DATA_ACTIVE_CONTRACT = "active_contract"
DATA_PAYMENT_PLANS = "payment_plans"
DATA_CLASSES = "classes"
DATA_CLASSES_TYPES = "classes_types"
DATA_INSTRUCTORS = "instructors"
DATA_CLASSES_VISITS = "classes_visits"
DATA_BOOKINGS = "bookings"
DATA_TIMELINE = "timeline"
DATA_CLUB = "club"
DATA_OPENING_HOURS = "opening_hours"

# Enriched/computed data keys
DATA_UPCOMING_CLASSES = "upcoming_classes"
DATA_TODAYS_CLASSES = "todays_classes"
DATA_NEXT_CLASS = "next_class"
DATA_NEXT_FAVORITE_CLASS = "next_favorite_class"
DATA_NEXT_FAVORITE_INSTRUCTOR_CLASS = "next_favorite_instructor_class"
DATA_RECOMMENDED_CLASS = "recommended_class"
DATA_WEEKLY_VISITS = "weekly_visits"
DATA_MONTHLY_VISITS = "monthly_visits"
DATA_NOTIFICATIONS = "notifications"
DATA_CLASS_BUDDIES = "class_buddies"

# Contract statuses from API
CONTRACT_STATUS_CURRENT = "Current"

# Vivertine club ID (discovered from API)
VIVERTINE_CLUB_ID = 129

# Sensor definitions
SENSOR_MEMBERSHIP_STATUS = "membership_status"
SENSOR_MEMBERSHIP_EXPIRY = "membership_expiry"
SENSOR_MEMBERSHIP_DAYS_LEFT = "membership_days_left"
SENSOR_MEMBERSHIP_PLAN = "membership_plan"
SENSOR_NEXT_CLASS = "next_class"
SENSOR_TODAYS_CLASSES = "todays_classes_count"
SENSOR_WEEKLY_VISITS = "weekly_visits"
SENSOR_MONTHLY_VISITS = "monthly_visits"
SENSOR_TOTAL_VISITS = "total_visits"
SENSOR_ACTIVE_BOOKINGS = "active_bookings"
SENSOR_NEXT_FAVORITE_CLASS = "next_favorite_class"
SENSOR_NEXT_FAVORITE_INSTRUCTOR_CLASS = "next_favorite_instructor_class"
SENSOR_RECOMMENDED_CLASS = "recommended_class"
SENSOR_LATEST_NOTIFICATION = "latest_notification"
SENSOR_CLASS_BUDDIES = "class_buddies"

# Service names
SERVICE_SEND_TEST_NOTIFICATION = "send_test_notification"
SERVICE_BOOK_CLASS = "book_class"
SERVICE_CANCEL_BOOKING = "cancel_booking"

SENSOR_TYPES = {
    SENSOR_MEMBERSHIP_STATUS: {
        "name": "Membership Status",
        "icon": "mdi:card-account-details",
        "unit": None,
        "device_class": None,
    },
    SENSOR_MEMBERSHIP_EXPIRY: {
        "name": "Membership Expiry",
        "icon": "mdi:calendar-clock",
        "unit": None,
        "device_class": "timestamp",
    },
    SENSOR_MEMBERSHIP_DAYS_LEFT: {
        "name": "Membership Days Left",
        "icon": "mdi:calendar-range",
        "unit": "days",
        "device_class": None,
    },
    SENSOR_MEMBERSHIP_PLAN: {
        "name": "Membership Plan",
        "icon": "mdi:card-account-details-outline",
        "unit": None,
        "device_class": None,
    },
    SENSOR_NEXT_CLASS: {
        "name": "Next Class",
        "icon": "mdi:dumbbell",
        "unit": None,
        "device_class": None,
    },
    SENSOR_TODAYS_CLASSES: {
        "name": "Today's Classes",
        "icon": "mdi:calendar-today",
        "unit": "classes",
        "device_class": None,
    },
    SENSOR_WEEKLY_VISITS: {
        "name": "Weekly Visits",
        "icon": "mdi:calendar-week",
        "unit": "visits",
        "device_class": None,
    },
    SENSOR_MONTHLY_VISITS: {
        "name": "Monthly Visits",
        "icon": "mdi:calendar-month",
        "unit": "visits",
        "device_class": None,
    },
    SENSOR_TOTAL_VISITS: {
        "name": "Total Visits",
        "icon": "mdi:counter",
        "unit": "visits",
        "device_class": None,
    },
    SENSOR_ACTIVE_BOOKINGS: {
        "name": "Active Bookings",
        "icon": "mdi:bookmark-check",
        "unit": "bookings",
        "device_class": None,
    },
    SENSOR_NEXT_FAVORITE_CLASS: {
        "name": "Next Favorite Class",
        "icon": "mdi:heart",
        "unit": None,
        "device_class": None,
    },
    SENSOR_NEXT_FAVORITE_INSTRUCTOR_CLASS: {
        "name": "Next Favorite Instructor Class",
        "icon": "mdi:account-heart",
        "unit": None,
        "device_class": None,
    },
    SENSOR_RECOMMENDED_CLASS: {
        "name": "Recommended Class",
        "icon": "mdi:star",
        "unit": None,
        "device_class": None,
    },
    SENSOR_LATEST_NOTIFICATION: {
        "name": "Latest Gym Notification",
        "icon": "mdi:bell",
        "unit": None,
        "device_class": None,
    },
    SENSOR_CLASS_BUDDIES: {
        "name": "Class Buddies",
        "icon": "mdi:account-group",
        "unit": "people",
        "device_class": None,
    },
}
