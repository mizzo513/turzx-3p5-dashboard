# TURZX V3.9.9 — configurable marquee and comprehensive current weather

Built on V3.9.8; preserve 480x320, display rotation, train data, USB recovery,
existing settings, and independent temperature / forecast provider selection.

## Marquee
- New setting: rail_scroll_speed_px_s (0-60 pixels per second).
- Default 9.4 px/s, equivalent to V3.9.8's approximately 9.41 px/s.
- 0 leaves the displayed text stationary.
- The existing 5fps target, adaptive USB bandwidth and clock-first priority remain.
- The setting is applied live without restarting the USB engine.

## Weather text editor
- Current temperature number and unit are now independent single-member groups.
- Editing one does not move, resize, or recolor the other.
- Optional explicit '現在気温（数値と単位 一括）' group still provides a grouped adjustment.
- Existing custom positions/colors are preserved, without changing layout_revision.

## Current weather: comprehensive judgement
- Ported the user's WeatherTransitWidget implementation.
- Priority: Japan Meteorological Agency rain nowcast (fresh positive rainfall)
  > nearby AMeDAS rainfall or observed sunshine > Open-Meteo current weather.
- Nearby recorded rain is labeled 雨(観測) or 雨(周辺); rain radar is 雨(実況).
- Forecast snow can help choose 雪 rather than 雨 for positive precipitation.
- Missing radar pixels or stale observations never imply 'no precipitation'.
- Fallback when all new sources are unavailable: keep the chosen weather
  provider's previous condition; no fabrication of normal/dry weather.
- Only current condition label and pictogram are replaced. Temperature, wind,
  humidity, daily highs/lows and precipitation probability remain from the
  selected provider (WeatherAPI.com/Open-Meteo).
- Independent observation requests occur asynchronously, no more frequently
  than every 5 minutes (with stale-evidence expiry). Non-working JMA website
  endpoints do not stall USB drawing; full errors are logged.

## Validation and limitations
- Automated tests validate radar/AMeDAS map decode, observation priority,
  model/provider fallback, user settings and individual unit editing.
- JMA tile/AMeDAS website endpoints are undocumented and may change.
- JMA observation is not a direct observation of the exact display location.
- Actual display speed and weather data quality require physical/online tests.
