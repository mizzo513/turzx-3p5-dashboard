# TURZX V3.9.23 — IR official live train tracking status

## New official live status source
- Read the data used by the official public train-position page:
  `https://www.ishikawa-railway.jp/api/v1/trains`.
- Parse and correlate `odpt:trainNumber`, `odpt:fromStation`,
  `odpt:toStation`, `odpt:railDirection`, `odpt:delay`,
  `@dc:date` and `@dct:valid` with the bundled timetable.
- Handle leading-zero API train numbers (e.g. `0639M` = `639M`).
- Evaluate each boarding station independently:
  - 加賀笠間 on the first leg
  - 金沢 on the second leg
- `正常` (green): observed in official live data, direction/position
  matches the planned leg, the boarding station is not yet passed,
  and reported delay is zero.
- `発車済` (grey): official position confirms the train has departed
  beyond **that leg's boarding station**.
- `発車前` (blue): scheduled departure remains in the future,
  but no individual active-train evidence exists.
- `遅延 N分` (yellow): positive `odpt:delay` or verified official
  per-train delay announcement, ahead of all positioning statuses.
- `取り止め` (red): a confirmed, date-/number-/segment-matched
  cancellation from the official railway announcements. This is
  higher priority than live positioning or delayed status.
- `未確認` (grey): the scheduled departure has passed with no
  trusted observation, or network data is unavailable/invalid.
  **Absence from the live feed does not establish an actual cancellation
  or station passage.**
- Position comparison includes route direction, geographic ordering of
  all 19 IR station codes, and optional next-station data.
- The feed's explicit validity window is enforced, with a maximum
  45-second grace for web/server-cache timing. No indefinite stale cache.
- Requests run asynchronously at 30 seconds by default, configurable
  20–120 seconds in the train settings; no browser, screenshot or OCR required.

## Preserved behavior
- Current three-card 480×320 layout and four independent scheduled time
  columns are unchanged.
- Transfer info remains `3→6　12分` with a **full-width space**.
- Weather, clock, USB panel and top IR/JR operations notification
  continue without coupling their refresh cycle to the live feed.
- Static timetable times and transfer feasibility are NOT updated for
  delays; this release adds live status labeling only.
- Official train data is a publicly visible website resource, not a
  third-party published stable integration API; the external contract
  may change, and continued automated use must respect provider terms.

## Tests
- Nine records patterned on actual 2026-11-25 08:56 official feed.
- Ahead/at/past either boarding station; opposite direction,
  malformed/duplicate/stale/offline feeds; delay/cancellation precedence.
- All existing GUI, USB, weather, timetable and updater regressions,
  frozen Windows EXE launch and updater installation.
