# TURZX V3.9.21 — train-specific status labels and unified platform/wait

## New compact transfer layout
- The labels 発 / 金沢着 / 金沢発 / 着 are no longer rendered in
  the three displayed train rows. Their four independent actual scheduled
  time columns remain in place.
- The space above the four times now shows the train number and status
  for **each** leg: 加賀笠間→金沢 and 金沢→津幡.
- Supported UI captions and colors:
  - `1649M 遅延 8分` (yellow) **only with explicit verified data**
  - `445M 正常` (green) **only with explicit train-specific evidence**
  - `333M 運休` (red) **only with confirmed matching cancellation**
  - `847M 発車前` (blue) if departure time is still in the future
    according to the static timetable (not a live proof of operation)
  - `443M 未確認` (grey) if it has departed without individual evidence
- Replace separate `乗換12分` and `3→6番線` entries with a fixed
  position combined `3→6/12分`, using '?' for unknown platform.
- Direct journeys still display `直通`, even when the train number changes
  at Kanazawa. For one-leg routes the train number and status are displayed
  with the original times and concise trip duration.
- User custom text positions/colors/panel styles and all three time cards
  remain editable; two new text IDs for each card are now available in the
  layout editor: `train_service_first_N`, `train_service_second_N`.
  Old station-label settings are retained in the settings file but unused.

## Official IR cancellation matching
- Additional asynchronous, rate-limited query of the **public** news
  listing and today's cancellation announcements at the existing rail
  status refresh interval (minimum five minutes).
- Strictly limit article links to the railway's own host, check the
  announced day, extract explicitly listed train numbers, and ensure
  the specified cancelled section overlaps the chosen leg.
- Example: the 2026-11-20 announcement explicitly cancels 333M,
  1649M and other services on specified sections. Statuses are matched
  by service ID rather than applying all-line statements to individual
  scheduled departures.
- Never declare `正常` just because an incident announcement is absent.
  Absence from the official cancellation notice is not a live train
  position update. A past/future train is shown conservatively if no
  verified train-specific data exists.
- The current public announcements do not provide reliable individual
  delay minutes. The rendering path can show `遅延 N分` if a verified
  record becomes available, but this release does NOT invent minutes or
  claim to perform full realtime GPS tracking.
- This does not change the official IR/JR single-line top notification,
  numeric marquee FPS, or 480x320 physical rotation. External source
  retrieval is isolated from the display sender thread.
- Local STATUS IPC additionally reports `train_operation_count`,
  `train_operation_error`, and `train_operations_updated`.

## Tests
- Official announcements: route-specific partial cancellation, full
  cancellation, date matching, irrelevant links and fetch failures.
- New visual labels in all three rows, two train IDs per transfer,
  color-coded verified statuses and exact `3→6/12分` display.
- Preserve 4 timestamps, direct/no-transfer, single-leg and uncertainty.
- Full preexisting GUI, clocks, USB partial transfer, rail and weather
  regressions; frozen Windows EXE and updater integration tests.

The runtime values are only as current as the original official website
and the user-selected refresh period (minimum 5 minutes). Always check
the railway's official live status before departing.
