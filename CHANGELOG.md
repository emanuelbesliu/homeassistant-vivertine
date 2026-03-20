# Changelog

## 1.0.3 (2026-03-20)

### Fixed
- Fix `AttributeError: 'HomeAssistant' object has no attribute 'components'` in alerts.py — replaced deprecated `hass.components.persistent_notification.async_create()` with `hass.services.async_call("persistent_notification", "create", ...)` for modern HA compatibility

## 1.0.2 (2026-03-19)

### Added
- New sensor: `next_favorite_class` — shows the next upcoming class matching configured favorite class types
- New sensor: `next_favorite_instructor_class` — shows the next upcoming class taught by a configured favorite instructor
- New option: **Favorite instructors** — comma-separated instructor names to monitor (same pattern as favorite classes)
- Alerts now also monitor classes taught by favorite instructors (cancellation, time change, instructor change, low spots)

## 1.0.1 (2026-03-19)

### Fixed
- Fix authentication: PerfectGym API wraps all responses in a `{"data": ..., "errors": ...}` envelope — token extraction and all data parsing now correctly unwraps this
- Fix account endpoint handling: Account API returns a list with a single object, now extracted properly
- Fix alerts.py: use DATA_CLASSES constant instead of hardcoded string, remove unused parameter

## 1.0.0 (2026-03-19)

### Added
- Initial release
- Membership monitoring (status, plan, expiry, days left)
- Class schedule with instructor names (joined from Instructors API)
- Visit tracking (weekly, monthly, total, recent history)
- Active bookings count
- Upcoming schedule sensor with full daily breakdown
- Favorite class alert system:
  - Class cancelled detection
  - Class time change detection
  - Instructor change detection
  - Low available spots alert
- Config flow with email/password authentication
- Options flow for favorites, notifications, update interval
- Romanian and English translations
- Persistent notifications + HA events for alerts
- Mobile push notifications via configurable notify service
