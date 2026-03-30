# Changelog

## 1.0.19 (2026-03-30)

### Fixed
- **Debug booking button on iOS** — added comprehensive logging and exception handling to the `mobile_app_notification_action` event handler to diagnose why the "Da, rezerva!" button was not working on iOS. The handler previously had no top-level exception guard, meaning any unexpected error would be silently swallowed by HA's event bus with no log output

### Technical
- Added early-exit guard for non-`VIVERTINE_` actions — avoids unnecessary debug logging for events from other integrations
- Added debug log at handler entry with full `action` value and raw `event.data` — confirms whether iOS actually fires the event and what action string it sends
- Wrapped the entire handler in a top-level `try/except Exception` with `_LOGGER.exception()` — any crash is now logged with full traceback instead of being silently eaten
- Extracted action processing into `_process_notification_action()` inner function for cleaner exception boundary
- Added `else` branch logging for unrecognized `VIVERTINE_*` action prefixes

## 1.0.18 (2026-03-20)

### Changed
- **Suppress booking suggestions when gym is closed** — booking suggestion notifications (including snoozed re-triggers) are no longer sent outside gym opening hours. Uses the existing `gym_busyness` "Inchis" (Closed) state from the OpeningHours API. Snoozed suggestions with expired cooldowns will naturally re-trigger on the first scan cycle after the gym opens

### Technical
- Added `BUSYNESS_LABEL_CLOSED` and `DATA_GYM_BUSYNESS` imports to `alerts.py`
- Early return in `_check_booking_suggestions()` when `gym_busyness.label == "Inchis"`

## 1.0.17 (2026-03-20)

### Added
- **Snooze button on booking suggestions** — actionable notifications now have a third button "Ma mai gandesc" ("Let me think about it") between "Da, rezerva!" and "Nu". Tapping it temporarily hides the suggestion for 1 hour (default cooldown), after which it re-triggers on the next coordinator update cycle. Unlike "Nu" (permanent dismiss), snooze is in-memory only — after HA restart, snoozed suggestions re-appear immediately (same as ignored notifications)

### Technical
- New constants in `const.py`: `ACTION_SNOOZE_PREFIX = "VIVERTINE_SNOOZE_"`, `DEFAULT_SNOOZE_COOLDOWN_SECONDS = 3600`
- New `_snoozed_suggestions` dict in `alerts.py` — maps `class_id` to `monotonic()` expiry timestamp. Checked on every coordinator update; expired entries are cleaned up automatically
- New `async_snooze_suggestion()` method in `alerts.py` — sets cooldown and removes class from `_sent_alerts` so it can re-trigger
- Snooze cooldown check integrated into `_check_booking_suggestions()` dedup logic (checked after `_sent_alerts` and `_dismissed_suggestions`)
- New `ACTION_SNOOZE_PREFIX` handler in `__init__.py` `_handle_notification_action` event listener

## 1.0.16 (2026-03-20)

### Added
- **Gym busyness "Inchis" (Closed) state** — the `gym_busyness` sensor now shows `Inchis` when the gym is outside its opening hours, instead of calculating busyness from class data. Uses the `/v1/Clubs/OpeningHours` API to determine if the gym is currently open. New attributes: `is_open` (true/false), `open_from`, `open_until` (today's hours). Falls back to "assume open" if opening hours data is unavailable
- **Persistent booking suggestion dedup** — dismissed booking suggestions ("Nu" button) are now persisted to disk via `homeassistant.helpers.storage.Store`. Previously, dismissed suggestions were lost on every HA restart/integration reload (in-memory `_sent_alerts` set). Now: if user tapped "Nu", the class ID is saved to `.storage/vivertine.dismissed_suggestions_{entry_id}` and never re-suggested. If user never responded, the suggestion re-sends after restart

### Technical
- New constant `BUSYNESS_LABEL_CLOSED = "Inchis"` in `const.py`
- New constants `STORAGE_VERSION` and `STORAGE_KEY` in `const.py` for persistent storage
- New static method `_is_gym_open()` in `coordinator.py` — filters opening hours by club ID, maps weekday to PerfectGym day names, handles `isClosed`/`isOpenTwentyFourHours`/`openTwentyFourSeven` flags
- `_compute_gym_busyness()` now accepts `opening_hours` parameter and returns `Inchis` with zeroed stats when gym is closed
- `alerts.py` now uses `Store` for persistent dismissed suggestions: `async_load_dismissed()` on startup, `async_dismiss_suggestion()` on "Nu" tap
- `__init__.py` calls `await alerts.async_load_dismissed()` on setup and persists dismiss actions

## 1.0.15 (2026-03-20)

### Added
- **Membership expiry notifications** — configurable reminders at specific day milestones (default: 60, 30, 14, 7 days) before expiry, plus daily notifications when days remaining drops below a threshold (default: 7 days). Also notifies on the actual expiry day (day 0). Never sends notifications after expiry. Configurable via options: `expiry_reminder_days` (comma-separated) and `expiry_daily_threshold` (1-30)
- **Gym busyness sensor** (`sensor.vivertine_gym_busyness`) — estimates current gym busyness from class attendee counts in a configurable time window (default: 4 hours). State is a categorical label: Liber (<30%), Moderat (30-70%), Aglomerat (>70%) based on total attendees vs total capacity. Attributes include occupancy_percent, total_attendees, total_capacity, classes_count, and a per-class breakdown (capped at 10)
- New HA event: `vivertine_membership_expiry` — fired alongside the notification for automation use
- New options: `expiry_reminder_days`, `expiry_daily_threshold`, `busyness_window_hours`

### Fixed
- **Class buddies 16KB recorder fix** — the `booked_classes` attribute was storing full attendee lists for ALL bookings (including ~70 past ones), exceeding HA's 16384-byte state attribute limit. Now filters to only upcoming booked classes (max 5), stores only buddy names instead of full attendee dicts, and caps `who_is_going` at 10 entries with a `who_is_going_total` count

## 1.0.14 (2026-03-20)

### Added
- **24-hour booking window enforcement** — Vivertine/PerfectGym only allows bookings within 24 hours of class start. The integration now validates this at every level:
  - **Booking suggestions** (`alerts.py`) — actionable push notifications are only sent for classes starting within 24h (not farther out)
  - **Book class service** (`vivertine.book_class`) — rejects booking attempts for classes >24h away with a clear Romanian error message
  - **Notification "Da, rezervă!" button** — validates 24h window before calling the API; sends "Rezervare indisponibilă" notification if too early
- **`bookable` attribute** on `next_class`, `next_favorite_class`, `next_favorite_instructor_class`, `recommended_class` sensors — `true`/`false` flag indicating whether the class is within the 24h booking window
- **`class_id` attribute** on `next_class`, `next_favorite_class`, `next_favorite_instructor_class`, `recommended_class`, and all schedule sensor entries — exposes the numeric class ID for use with `vivertine.book_class` service
- **`bookable` flag in schedule sensor** — each class entry in the upcoming schedule now shows whether it can be booked right now

### Technical
- New constant `BOOKING_WINDOW_HOURS = 24` in `const.py`
- New helper `_check_booking_window()` in `__init__.py` — looks up class start time from coordinator data, returns `None` if bookable or a Romanian error message if not
- New helper `_is_class_bookable()` in `sensor.py` — pure function for the `bookable` attribute computation
- Booking suggestion dedup now also skips classes that already started

## 1.0.13 (2026-03-20)

### Added
- **Actionable booking suggestions** — when a recommended, favorite, or favorite-instructor class is detected as unbooked with available spots, the integration sends an actionable push notification to your phone with "Da, rezervă!" and "Nu" buttons. Tapping "Da, rezervă!" books the class automatically and sends a confirmation notification
- **Smart deduplication** — if 2-3 recommendation types (recommended + favorite + favorite instructor) point to the same class, only ONE notification is sent with a combined reason (e.g., "Clasă recomandată + favorită")
- **Buddy enrichment in suggestions** — booking suggestion notifications mention which buddies are already going to the class (e.g., "Ana M. și Mihai P. participă!")
- **`buddies_going` attribute** on `next_favorite_class`, `next_favorite_instructor_class`, and `recommended_class` sensors — shows which buddies are signed up for that class (even if you haven't booked it)
- New HA event: `vivertine_booking_suggestion` — fired alongside the notification for automation use

### Technical
- New `_check_booking_suggestions()` method in `alerts.py` — runs on every coordinator update, checks three recommendation sources, deduplicates by class ID, respects booking/spots/already-suggested filters
- New `_send_actionable_notification()` method in `alerts.py` — sends mobile push with `data.actions` and `data.tag` for iOS/Android Companion App
- New `mobile_app_notification_action` event listener in `__init__.py` — handles "Da, rezervă!" button taps by calling `api.book_class()`, refreshing coordinator, and sending confirmation
- Error notification on booking failure ("Nu am putut rezerva clasa: ...")
- Proper cleanup: unsub for notification action listener in `async_unload_entry()`
- New coordinator key `buddies_by_class` in `_build_class_buddies()` — maps ANY classId to buddy name list (not just booked classes)

## 1.0.12 (2026-03-20)

### Fixed
- **Buddy detection bug** — buddies were never detected (`is_buddy` always `false`) because `classes_visits` API has no `classId` field. Switched buddy detection to use `bookings` data (which has `classId` for both past and future bookings) instead of `classes_visits`
- **Performance optimization** — replaced O(n^3) nested-loop buddy detection with O(n) pre-built `person_to_class_ids` index. For each attendee, buddy status is now a single set-difference check instead of scanning all other classes' attendee lists

## 1.0.11 (2026-03-20)

### Added
- **Class Buddies** sensor (`class_buddies`) — shows who's going to your next booked class. State = attendee count, attributes include full attendee lists per booked class with buddy highlighting
- **Buddy detection** — cross-references class attendees with your visit history to flag people you've previously worked out with as "buddies" (`is_buddy: true`)
- **Privacy-first**: attendee names displayed as first name + last initial (e.g. "Emanuel B."), no photos or social media exposed
- **Enriched existing sensors**: `next_class` and `active_bookings` now include `who_is_going` attendee lists in their attributes
- Attendees sorted with buddies first, then alphabetical; standby status included

### Technical
- New API method: `get_who_is_in()` fetches full attendee list from `GET /v1/Classes/WhoIsIn` endpoint (~10K entries)
- WhoIsIn fetch is fault-tolerant (wrapped in try/except, like notifications)
- New coordinator method: `_build_class_buddies()` processes attendee data, filters by booked classes, detects buddies via visit history cross-reference

## 1.0.10 (2026-03-20)

### Removed
- **Gym Occupancy** sensors (`gym_occupancy`, `gym_capacity`, `gym_occupancy_percent`) — Vivertine's PerfectGym instance returns `null` for all occupancy fields (`WhoIsInCount.count`, `Limits.limit`, `Limits.currentlyInClubCount`), making these sensors permanently "Unknown". Removed entirely: constants, API methods, coordinator fetch blocks, and sensor logic.

## 1.0.9 (2026-03-20)

### Added
- **Gym Occupancy** sensors: real-time people count (`gym_occupancy`), club capacity limit (`gym_capacity`), and computed occupancy percentage (`gym_occupancy_percent`) — data from PerfectGym `WhoIsInCount` and `Limits` APIs
- **Latest Gym Notification** sensor (`latest_notification`): shows the most recent gym notification subject/content, with full list of recent notifications in attributes
- **Class Booking** services:
  - `vivertine.book_class` — book a class by its class ID (triggers coordinator refresh after booking)
  - `vivertine.cancel_booking` — cancel a booking by its booking ID (triggers coordinator refresh after cancellation)
- Service descriptions in `strings.json` and translations (English + Romanian)

### Changed
- Service constants (`SERVICE_SEND_TEST_NOTIFICATION`, `SERVICE_BOOK_CLASS`, `SERVICE_CANCEL_BOOKING`) moved to `const.py` — removed inline definition in `__init__.py`
- Occupancy and notification data fetches are fault-tolerant: failures log a debug message and continue without breaking the update cycle

## 1.0.8 (2026-03-20)

### Added
- Full CI/CD pipeline: 8 GitHub Actions workflows (validate, release, release-please, dependencies, codeql, stale, validate-workflows, dependabot-auto-merge)
- Dependabot configuration for automated dependency updates (pip + github-actions)
- `requirements.txt` for dependency validation and tracking
- Repository topics for HACS compatibility (`hacs`, `home-assistant`, `custom-component`, `smart-home`, `vivertine`, `gym`, `perfectgym`)

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
