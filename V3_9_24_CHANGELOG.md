# TURZX V3.9.24 — early false "発車済" fix and live diagnostics

## Fixed
- A train scheduled to depart 加賀笠間 at **09:25** (e.g., 639M)
  could have appeared as `発車済` at **09:21** because the old classifier
  trusted the public live-position row without comparing the boarding time.
- For all train connections, including 金沢→津幡, compare **both**
  (1) display time and (2) the official observation timestamp
  against the actual **leg's boarding departure** before confirming
  that the train has already passed the station.
- If the position claims a passed boarding station *before* the scheduled
  departure, show **`未確認`** instead of `発車済` and explain the
  discrepancy. A stale predeparture observation is still not enough to
  claim `発車済` immediately after the timetable departure.
- Distinguish `fromStation = boarding station` with no next-station
  departure record (stopped: `正常`) from `fromStation = boarding`
  with a next-station record (passed: `発車済` only when time-valid).
- Positive per-train delay and confirmed date/section-specific cancellation
  still take precedence (`遅延 N分` / `取り止め`).
- Missing/stale/invalid live data never proves departure.

## Diagnostics
- New settings tab button **「在線判定の詳細」**.
- Read the active display engine's **cached** official train feed
  over the localhost status channel (no extra HTTP requests).
- Display, for each of up to three train choices and both legs:
  train number, visible status, boarding/destination, scheduled departure,
  API's current/next station, observed timestamp, validity deadline,
  delay minutes, classification, and reason.
- A contradiction is explicitly identified so users can report it
  without manually collecting network captures.
- Diagnostic data is exposed in runtime status under
  `train_live_diagnostics`, including a boolean `contradiction`.
- The diagnostic window scrolls and provides a Copy button.

## Preserved
- Scheduled four time cells, transfer `5→7　3分` format, train cards,
  official train data source, live polling configuration, weather,
  USB/clock behavior, and local updater.

## Regression coverage
- Exact scenario 2026-11-25 09:21, 639M 09:25 planned departure.
- API position past departure station, boarding with/without next station.
- Both current/observation timestamps, after-departure and stale cases,
  cancellation/delay priority, two-leg diagnostics and previous suites.
