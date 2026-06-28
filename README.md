# Deye Cloud EMS — Home Assistant Integration

Custom HACS integration for **Deye Cloud OpenAPI** with full EMS control and **Thai TOU (MEA/PEA) intelligence**.

Most existing Deye integrations are read-only. This integration adds official cloud **monitoring + control**: TOU schedules, battery parameters, work mode, solar sell, and automation services designed for Thailand's Time-of-Use electricity tariff.

## Features

- Real-time monitoring (SOC, PV, grid, load, battery, temperature, energy)
- **Set TOU** schedules via API or named profiles
- **Battery parameters** (charge/discharge current, reserve SOC)
- **Work mode** and **energy pattern** control
- **Solar sell** and **grid charge** switches
- Thai TOU awareness (Peak 09:00–22:00 Mon–Fri, Off-Peak otherwise)
- Built-in profiles: `thai_sunny`, `thai_rainy`, `thai_holiday` (minimum reserve **20%** for battery health)
- Services for automations and 6 blueprints

## Installation

### HACS (recommended)

1. Add this repository as a custom HACS integration
2. Install **Deye Cloud EMS**
3. Restart Home Assistant
4. Go to **Settings → Devices & Services → Add Integration → Deye Cloud EMS**

### Manual

Copy `custom_components/deyecloud_ems/` into your Home Assistant `config/custom_components/` directory and restart.

## API Credentials

1. Register at [Deye Cloud Developer Portal](https://developer.deyecloud.com/start)
2. Create an app at [developer.deyecloud.com/app](https://developer.deyecloud.com/app)
3. Note your **App ID** and **App Secret**
4. Choose the correct base URL:

| Region | Base URL |
|--------|----------|
| Europe / Asia-Pacific | `https://eu1-developer.deyecloud.com/v1.0` |
| Americas | `https://us1-developer.deyecloud.com/v1.0` |

## Configuration

| Field | Description |
|-------|-------------|
| Username / Email | Deye Cloud login |
| Password | Deye Cloud password |
| App ID | From developer portal |
| App Secret | From developer portal |
| Base URL | Regional API URL |
| Company ID | Optional, for installer/business accounts |
| Scan interval | 30–300 seconds (default 60) |

## Thai TOU Savings Guide

Thailand MEA/PEA TOU (2026):

| Period | Hours | Rate (THB/kWh) |
|--------|-------|----------------|
| **Peak** | 09:00–22:00 Mon–Fri | 4.1025 |
| **Off-Peak** | 22:00–09:00 + weekends/holidays | 2.5849 |

**Battery arbitrage**: every 1 kWh discharged during Peak instead of buying from grid saves **~1.52 THB**.

Example: 10 kWh battery fully arbitraged daily ≈ **450 THB/month** savings.

### Integration entities for TOU

| Entity | Purpose |
|--------|---------|
| `sensor.*_thai_tou_rate_now` | Current electricity rate (THB/kWh) |
| `sensor.*_thai_tou_period` | "Peak" or "Off-Peak" |
| `binary_sensor.*_is_peak_now` | True during peak hours |
| `binary_sensor.*_is_thai_holiday` | True on public holidays |
| `sensor.*_active_tou_profile` | Last applied profile name |
| `sensor.*_battery_soc_predicted_17h` | Estimated SOC at 17:00 |

## Services

| Service | Description |
|---------|-------------|
| `deyecloud_ems.set_tou` | Push raw TOU schedule |
| `deyecloud_ems.apply_tou_profile` | Apply named profile |
| `deyecloud_ems.set_reserve` | Set battery reserve SOC |
| `deyecloud_ems.smart_reserve` | Auto reserve from forecast |
| `deyecloud_ems.smart_night_charge` | Decide grid charge tonight |
| `deyecloud_ems.set_battery_parameter` | Generic battery parameter |
| `deyecloud_ems.set_work_mode` | Set work mode |
| `deyecloud_ems.set_energy_pattern` | Set energy pattern |
| `deyecloud_ems.set_solar_sell` | Enable/disable solar sell |

## Blueprints

Located in `blueprints/automation/`:

| Blueprint | Schedule | Purpose |
|-----------|----------|---------|
| `deyecloud_ems_thai_daily_smart` | 06:00, 11:00, 17:00, 22:00 | Full 4-step Thai TOU logic |
| `deyecloud_ems_smart_night_charge` | 21:30 | Grid charge decision from tomorrow forecast |
| `deyecloud_ems_solar_sell_window` | SOC changes | Smart solar sell during peak |
| `deyecloud_ems_holiday_mode` | Holiday detected | Flat holiday profile |
| `deyecloud_ems_sunny_day` | Input boolean | Force sunny profile |
| `deyecloud_ems_rainy_day` | Input boolean | Force rainy profile |

Import blueprints via **Settings → Automations → Blueprints → Import Blueprint**.

## Pairing with Solcast (recommended)

[Solcast HA integration](https://github.com/BJReplay/ha-solcast-solar) provides accurate PV forecasts for your panels.

1. Register free at [toolkit.solcast.com.au](https://toolkit.solcast.com.au) (Hobby plan: 10 calls/day)
2. Install Solcast via HACS
3. Configure panel size, tilt, and azimuth
4. Use these sensors in blueprints:
   - `sensor.solcast_forecast_today` — morning profile selection (06:00)
   - `sensor.solcast_forecast_tomorrow` — night charge decision (21:30)

**Without Solcast**: use Open-Meteo solar sensors or any kWh forecast sensor. Forecast input is optional; automations fall back to SOC-only logic.

## Example: 4-step daily automation

```
06:00  Check forecast → apply thai_sunny or thai_rainy profile
11:00  If PV underperforming → raise reserve to 50%
17:00  If SOC >= 80% → SELLING_FIRST (discharge during peak)
       If SOC >= 40% → BATTERY_FIRST
       Else → LOAD_FIRST (preserve battery)
22:00  Off-peak → ZERO_EXPORT_TO_LOAD, BATTERY_FIRST, reserve 20%
```

## Built-in TOU Profiles

### thai_sunny
Solar charge during the day, discharge during peak, hold at night — no grid charge.

### thai_rainy
Same strategy as sunny; relies on available solar only, no grid charge.

### thai_holiday
Off-peak hold with solar top-up if available — no grid charge.

Minimum battery reserve SOC is **20%** across profiles. Grid charging is not used (EV is on a separate circuit).

## Cost tracking (optional HA helpers)

Create **Riemann sum integral** helpers on `sensor.*_grid_power` to track kWh, then template sensors multiplying by `sensor.*_thai_tou_rate_now` for daily THB cost.

## Troubleshooting

- Check **Settings → System → Logs** for `deyecloud_ems` errors
- Verify App ID/Secret and region URL in the developer portal
- For installer accounts, set **Company ID**
- Increase scan interval if you hit API rate limits

## References

- [Deye Cloud Developer Portal](https://developer.deyecloud.com/start)
- [Official sample code](https://github.com/DeyeCloudDevelopers/deye-openapi-client-sample-code)
- [hass-deyecloud (read-only reference)](https://github.com/heavenknows1978/hass-deyecloud)

## License

MIT

## Disclaimer

This is a community integration, not officially supported by Deye. Use at your own risk.
