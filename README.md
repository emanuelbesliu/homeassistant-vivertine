# Vivertine Gym - Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Custom Home Assistant integration for **Vivertine Gym** (Iași, Romania), built on the [PerfectGym](https://www.perfectgym.com/) platform.

## Features

- **Membership monitoring** — status, plan name, expiry date, days remaining
- **Class schedule** — upcoming classes with instructor names, time slots, available spots, and zones
- **Visit tracking** — weekly/monthly/total visit counts, recent visit history
- **Booking status** — active bookings count and standby positions
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
| `sensor.vivertine_next_class` | Next upcoming class name and instructor |
| `sensor.vivertine_next_favorite_class` | Next upcoming class matching favorite class types |
| `sensor.vivertine_next_favorite_instructor_class` | Next upcoming class by a favorite instructor |
| `sensor.vivertine_todays_classes_count` | Number of classes today |
| `sensor.vivertine_weekly_visits` | Club visits in the last 7 days |
| `sensor.vivertine_monthly_visits` | Club visits in the last 30 days |
| `sensor.vivertine_total_visits` | Total club visits |
| `sensor.vivertine_active_bookings` | Number of active class bookings |
| `sensor.vivertine_upcoming_schedule` | Full upcoming schedule (in attributes) |

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
