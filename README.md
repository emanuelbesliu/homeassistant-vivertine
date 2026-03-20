# Vivertine Gym - Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/emanuelbesliu/homeassistant-vivertine)](https://github.com/emanuelbesliu/homeassistant-vivertine/releases/latest)
[![License](https://img.shields.io/github/license/emanuelbesliu/homeassistant-vivertine)](LICENSE)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/emanuelbesliu)

Custom Home Assistant integration for **Vivertine Gym** (Iași, Romania), built on the [PerfectGym](https://www.perfectgym.com/) platform.

## Features

- **Membership monitoring** — status, plan name, expiry date, days remaining
- **Class schedule** — upcoming classes with instructor names, time slots, available spots, and zones
- **Visit tracking** — weekly/monthly/total visit counts, recent visit history
- **Booking status** — active bookings count and standby positions
- **Favorite classes & instructors** — dedicated sensors for your preferred class types and instructors
- **Recommended class** — smart recommendation based on your attendance history
- **Smart alerts** for favorite classes:
  - Class cancelled
  - Class time changed
  - Instructor changed
  - Available spots below threshold (default: 5)

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add `https://github.com/emanuelbesliu/homeassistant-vivertine` as an **Integration**
4. Search for "Vivertine" and install
5. Restart Home Assistant

### Manual

1. Copy `custom_components/vivertine/` to your HA `custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Vivertine Gym**
3. Enter your Vivertine (PerfectGym) email and password
4. Optionally adjust the update interval (default: 5 minutes)

### Options

After setup, configure options via the integration's **Configure** button:

| Option | Description | Default |
|--------|-------------|---------|
| Update interval | Data fetch frequency (60-3600s) | 300s |
| Favorite classes | Comma-separated class names to monitor | *(empty)* |
| Favorite instructors | Comma-separated instructor names to monitor | *(empty)* |
| Notification service | HA notify service target (e.g., `mobile_app_iphone`) | *(empty)* |
| Low spots threshold | Alert when spots drop below this | 5 |

## Sensors

| Sensor | Description |
|--------|-------------|
| `sensor.vivertine_membership_status` | Current membership status (Current/Expired) |
| `sensor.vivertine_membership_expiry` | Membership expiration date |
| `sensor.vivertine_membership_days_left` | Days until membership expires |
| `sensor.vivertine_membership_plan` | Active plan name |
| `sensor.vivertine_next_class` | Next upcoming class with instructor and time |
| `sensor.vivertine_next_favorite_class` | Next upcoming class matching favorite class types |
| `sensor.vivertine_next_favorite_instructor_class` | Next upcoming class by a favorite instructor |
| `sensor.vivertine_recommended_class` | Recommended class based on attendance history |
| `sensor.vivertine_todays_classes_count` | Number of classes today |
| `sensor.vivertine_weekly_visits` | Club visits in the last 7 days |
| `sensor.vivertine_monthly_visits` | Club visits in the last 30 days |
| `sensor.vivertine_total_visits` | Total club visits |
| `sensor.vivertine_active_bookings` | Number of active class bookings |
| `sensor.vivertine_upcoming_schedule` | Full upcoming schedule (in attributes) |

### Class sensor display format

All class sensors (`next_class`, `next_favorite_class`, `next_favorite_instructor_class`, `recommended_class`) display the state in a human-readable format:

- **Today**: `Cycling — Ana Popescu @ 18:00`
- **Tomorrow**: `Yoga — Mihai Ion @ Mâine 10:00`
- **Other days**: `TRX — Ana Popescu @ Miercuri 19:00`

Day names are shown in Romanian. Each class sensor also provides detailed attributes (instructor, start/end time, zone, available spots, attendees, limit).

### Recommended class sensor

The `recommended_class` sensor uses a scoring algorithm based on your attendance history:

- Counts how many times you attended each class type (from visit history)
- Scores each upcoming class: `attendance_count × 2`
- Returns the highest-scoring upcoming class (earlier classes win ties)
- Extra attributes include `recommendation_score` and `type_attendance_count`

## Services

| Service | Description |
|---------|-------------|
| `vivertine.send_test_notification` | Send a test notification to verify the alert pipeline |

## Alert Events

When favorite classes or favorite instructors are configured, the integration fires these HA events:

| Event | Description |
|-------|-------------|
| `vivertine_class_cancelled` | A favorite class was cancelled |
| `vivertine_class_moved` | A favorite class time was changed |
| `vivertine_class_instructor_changed` | Instructor changed for a favorite class |
| `vivertine_class_low_spots` | Available spots dropped below threshold |

Each event includes: `class_name`, `instructor`, `start_date`, `message`, `title`.

## API

This integration uses the PerfectGym REST API (`goapi2.perfectgym.com`) with the Vivertine white-label configuration. Authentication is via email/password with a bearer token.

## License

MIT

## Credits

- **Author**: [@emanuelbesliu](https://github.com/emanuelbesliu)
- **Gym**: [Vivertine](https://vivertine.ro) — Anastasie Panu nr.26, Iași, Romania
- **Platform**: [PerfectGym](https://www.perfectgym.com/)

## ☕ Support the Developer

If you find this project useful, consider buying me a coffee!

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://buymeacoffee.com/emanuelbesliu)

## Disclaimer

This integration is not affiliated with, endorsed by, or supported by Vivertine or PerfectGym. Use at your own risk.
