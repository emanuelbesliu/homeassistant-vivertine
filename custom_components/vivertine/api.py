"""API client for the PerfectGym / Vivertine API."""

import logging
from datetime import datetime, timedelta
from typing import Any

import requests

from .const import (
    API_BASE_URL,
    WHITE_LABEL_ID,
    ENDPOINT_LOGIN,
    ENDPOINT_ACCOUNT,
    ENDPOINT_CLUBS,
    ENDPOINT_OPENING_HOURS,
    ENDPOINT_CONTRACTS,
    ENDPOINT_PAYMENT_PLANS,
    ENDPOINT_CHARGES,
    ENDPOINT_CLASSES,
    ENDPOINT_CLASSES_TYPES,
    ENDPOINT_CLASSES_VISITS,
    ENDPOINT_BOOKINGS,
    ENDPOINT_INSTRUCTORS,
    ENDPOINT_TIMELINE,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 20

USER_AGENT = (
    "PerfectGym/3.0 (iOS; Vivertine) "
    "HomeAssistant/2024.1 Integration"
)


class VivertineApiError(Exception):
    """General API error."""


class VivertineAuthError(VivertineApiError):
    """Authentication error (bad credentials or expired token)."""


class VivertineAPI:
    """Client for the PerfectGym (Vivertine) REST API.

    All methods are synchronous (use requests.Session).
    The coordinator wraps calls in async_add_executor_job.
    """

    def __init__(self, email: str, password: str) -> None:
        """Initialize the API client."""
        self._email = email
        self._password = password
        self._token: str | None = None
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        """Log in and obtain a bearer token.

        Returns True on success.

        Raises:
            VivertineAuthError: On invalid credentials or login failure.
        """
        payload = {
            "email": self._email,
            "password": self._password,
            "clientApplicationInfo": {
                "type": "WhiteLabel",
                "whiteLabelId": WHITE_LABEL_ID,
            },
        }
        try:
            resp = self._session.post(
                f"{API_BASE_URL}{ENDPOINT_LOGIN}",
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.exceptions.RequestException as err:
            raise VivertineApiError(
                f"Connection error during login: {err}"
            ) from err

        if resp.status_code == 401:
            raise VivertineAuthError("Invalid email or password")
        if resp.status_code == 500:
            raise VivertineApiError(
                f"Server error during login (HTTP 500): {resp.text[:200]}"
            )
        if resp.status_code != 200:
            raise VivertineApiError(
                f"Login failed with HTTP {resp.status_code}: {resp.text[:200]}"
            )

        try:
            data = resp.json()
        except ValueError as err:
            raise VivertineApiError(
                f"Invalid JSON in login response: {err}"
            ) from err

        # Token is nested under "data" key: {"data": {"token": "..."}}
        inner = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
        token = inner.get("token") or data.get("token")
        if not token:
            raise VivertineAuthError(
                "Login response did not contain a token"
            )

        self._token = token
        self._session.headers["Authorization"] = f"bearer {token}"
        _LOGGER.debug("Vivertine authentication successful")
        return True

    def validate_connection(self) -> bool:
        """Authenticate and verify the API returns valid data.

        Raises:
            VivertineAuthError: On bad credentials.
            VivertineApiError: On connection/API errors.
        """
        self.authenticate()
        # Quick check — fetch account info
        account = self.get_account()
        if not account:
            raise VivertineApiError("API returned empty account data")
        return True

    # ------------------------------------------------------------------
    # Private request helper
    # ------------------------------------------------------------------

    def _get(self, endpoint: str, params: dict | None = None) -> Any:
        """Make an authenticated GET request.

        Raises:
            VivertineAuthError: If token expired (HTTP 401).
            VivertineApiError: On any other error.
        """
        if not self._token:
            self.authenticate()

        url = f"{API_BASE_URL}{endpoint}"
        try:
            resp = self._session.get(
                url, params=params, timeout=REQUEST_TIMEOUT
            )
        except requests.exceptions.Timeout as err:
            raise VivertineApiError(
                f"Timeout connecting to {endpoint}: {err}"
            ) from err
        except requests.exceptions.ConnectionError as err:
            raise VivertineApiError(
                f"Connection error to {endpoint}: {err}"
            ) from err
        except requests.exceptions.RequestException as err:
            raise VivertineApiError(
                f"Request error to {endpoint}: {err}"
            ) from err

        if resp.status_code == 401:
            # Token might have expired — try re-auth once
            _LOGGER.debug("Got 401, attempting re-authentication")
            self.authenticate()
            try:
                resp = self._session.get(
                    url, params=params, timeout=REQUEST_TIMEOUT
                )
            except requests.exceptions.RequestException as err:
                raise VivertineApiError(
                    f"Request error on retry to {endpoint}: {err}"
                ) from err
            if resp.status_code == 401:
                raise VivertineAuthError(
                    "Authentication failed after token refresh"
                )

        if resp.status_code != 200:
            raise VivertineApiError(
                f"HTTP {resp.status_code} from {endpoint}: {resp.text[:200]}"
            )

        try:
            result = resp.json()
        except ValueError as err:
            raise VivertineApiError(
                f"Invalid JSON from {endpoint}: {err}"
            ) from err

        # API wraps responses in {"data": ..., "errors": ...}
        if isinstance(result, dict) and "data" in result:
            errors = result.get("errors")
            if errors:
                _LOGGER.warning(
                    "API returned errors from %s: %s", endpoint, errors
                )
            return result["data"]

        return result

    # ------------------------------------------------------------------
    # Account & membership
    # ------------------------------------------------------------------

    def get_account(self) -> dict[str, Any]:
        """Fetch user account/profile info."""
        data = self._get(ENDPOINT_ACCOUNT)
        # API returns a list with a single account object
        if isinstance(data, list) and data:
            return data[0]
        return data if isinstance(data, dict) else {}

    def get_contracts(self) -> list[dict[str, Any]]:
        """Fetch all user contracts (membership subscriptions)."""
        data = self._get(ENDPOINT_CONTRACTS)
        return data if isinstance(data, list) else []

    def get_payment_plans(self) -> list[dict[str, Any]]:
        """Fetch payment plan details (plan names, prices)."""
        data = self._get(ENDPOINT_PAYMENT_PLANS)
        return data if isinstance(data, list) else []

    def get_charges(self) -> list[dict[str, Any]]:
        """Fetch contract charges/payment history."""
        data = self._get(ENDPOINT_CHARGES)
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Club info
    # ------------------------------------------------------------------

    def get_clubs(self) -> list[dict[str, Any]]:
        """Fetch all clubs."""
        data = self._get(ENDPOINT_CLUBS)
        return data if isinstance(data, list) else []

    def get_opening_hours(self) -> list[dict[str, Any]]:
        """Fetch club opening hours."""
        data = self._get(ENDPOINT_OPENING_HOURS)
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Classes & schedule
    # ------------------------------------------------------------------

    def get_classes(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch classes (schedule).

        Args:
            start_date: ISO date string (YYYY-MM-DD). Defaults to today.
            end_date: ISO date string. Defaults to 7 days from start.
        """
        if not start_date:
            start_date = datetime.now().strftime("%Y-%m-%d")
        if not end_date:
            end = datetime.now() + timedelta(days=7)
            end_date = end.strftime("%Y-%m-%d")

        params = {"startDate": start_date, "endDate": end_date}
        data = self._get(ENDPOINT_CLASSES, params=params)
        return data if isinstance(data, list) else []

    def get_classes_types(self) -> list[dict[str, Any]]:
        """Fetch class type definitions (names, descriptions, photos)."""
        data = self._get(ENDPOINT_CLASSES_TYPES)
        return data if isinstance(data, list) else []

    def get_classes_visits(self) -> list[dict[str, Any]]:
        """Fetch user's class visit history."""
        data = self._get(ENDPOINT_CLASSES_VISITS)
        return data if isinstance(data, list) else []

    def get_bookings(self) -> list[dict[str, Any]]:
        """Fetch user's class bookings."""
        data = self._get(ENDPOINT_BOOKINGS)
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Instructors
    # ------------------------------------------------------------------

    def get_instructors(self) -> list[dict[str, Any]]:
        """Fetch all instructors."""
        data = self._get(ENDPOINT_INSTRUCTORS)
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Timeline (check-in history)
    # ------------------------------------------------------------------

    def get_timeline(self) -> list[dict[str, Any]]:
        """Fetch user's timeline (club visits / check-ins)."""
        data = self._get(ENDPOINT_TIMELINE)
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the HTTP session."""
        self._session.close()
