# Changelog

## 1.0.7 (2026-03-20)

### Fixed
- Fix alerts firing for past classes — `_build_class_snapshot()` now filters out classes whose `startDate` is in the past, preventing stale notifications (e.g., low-spots alerts for classes already held)
- Fix false "class cancelled" alerts when a class naturally transitions from future to past between coordinator update cycles — now checks if the class start time has passed before treating a snapshot disappearance as a cancellation

## 1.0.6 (2026-03-20)

### Added
- New sensor: `recommended_class` — recommends the best upcoming class based on your attendance history (scores by class type frequency)
- Improved class sensor display format for all class sensors (`next_class`, `next_favorite_class`, `next_favorite_instructor_class`, `recommended_class`):
  - Shows date and time alongside class name and instructor
  - Format: `"ClassName — Instructor @ 18:00"` (today), `"ClassName — Instructor @ Mâine 18:00"` (tomorrow), `"ClassName — Instructor @ Miercuri 18:00"` (other days)
  - Day names in Romanian
- `recommended_class` sensor attributes include `recommendation_score` and `type_attendance_count`
- README: added Buy Me a Coffee badges, new sensor documentation, display format documentation, disclaimer section

## 1.0.5 (2026-03-20)

### Added
- New service `vivertine.send_test_notification` — trigger a test notification from Developer Tools > Services to verify the alert pipeline (persistent notification + mobile push) is working

## 1.0.4 (2026-03-20)

### Added
- Add Vivertine brand icon for HA integration UI (`custom_components/vivertine/brand/icon.png` and `icon@2x.png`)

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
