# TURZX V3.9.19 — manual NTP refresh, status colon fix and simpler setup

## NTP manual synchronization (表示・時計 tab)
- Add "NTPサーバーと今すぐ同期" button immediately after the
  configured NTP server and automatic synchronization interval.
- The GUI sends a localhost-only SYNC_NTP IPC command to the **running
  display engine**, not to an unrelated GUI copy of the clock.
- The engine processes manual requests **regardless of ntp_sync_minutes**,
  asynchronously via the existing ThreadPoolExecutor and query_ntp.
- If the automatic NTP request is already in flight, one manual request
  is retained and run once that finishes; outdated frames are not blocked.
- Continue the normal periodic NTP schedule after manual sync. The
  Windows system clock is never modified.
- The button's adjacent status text reports request sent, in progress,
  successful synchronization, or a specific error/timeout. The engine
  exposes ntp_manual_pending / ntp_manual_running / ntp_manual_completed,
  ntp_manual_result, ntp_manual_error and ntp_manual_result_at in local
  runtime STATUS IPC.
- With the app stopped the button explains that the display must be
  started. If the NTP server field has unsaved edits, save first;
  the button uses the actively configured server.

## Status timestamp correction
- Fix doubled colon such as "11:03::23" in the settings screen's
  left-bottom "動作中" status. The minute-only IPC substring now removes
  ":SS" instead of just "SS". The on-device date/time drawing remains
  unchanged and uses one separator.
- Supports both 12-hour/24-hour and seconds ON/OFF.

## Google Routes
- Remove the optional "Google Routes APIキー" entry from the transit
  settings tab. Existing saved keys, the legacy Google route mode and
  backend compatibility remain intact; only the unnecessary input UI
  is removed. The standard bundled IR train source is unchanged.

## Tests
- Windows GUI test for the new manual sync button, running/stopped
  engine, NTP success/failure, unsaved settings and hidden API input.
- Localhost IPC request round-trip with an ephemeral test port.
- NTP clock accept and single-colon clock formatting regressions.
- Existing official rail, image-delta marquee, weather, USB and
  updater tests and Windows executable integration checks.
