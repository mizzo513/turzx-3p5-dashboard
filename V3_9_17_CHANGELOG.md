# TURZX V3.9.17 — numeric scrolling FPS and fixed/adaptive modes

Based on V3.9.16. Retains actual changed-pixel RGB565 patches,
USB reconnect and official rail-status text.

## New settings in the 乗換 tab
- スクロール更新頻度（fps）: accepts a number including decimals,
  from 1.0 to 30.0. Default 10.0.
- fpsの制御方式:
  - 固定（指定fps）: attempts regular frames at user-specified FPS.
    Slow USB transfers still physically limit delivered frames; never
    queue stale scroll positions.
  - 自動調整（転送速度に応じて低下）: user FPS is a maximum and
    previously established USB transfer-time EMA with 1.5x margin
    reduces attempted frequency when needed.
- Keeps 横スクロール速度（px/秒） independent of FPS.
- FPS and mode apply while the app is already running after saving;
  existing V3.9.16 and older settings silently default to adaptive 10.
- Monotonic absolute frame deadlines replace tick+interval to avoid
  accumulated scheduling delay. Frames dropped on overload do not queue.
- Runtime STATUS now additionally exposes scroll_fps_mode.
- Clock USB packets, display reconnect and status polling are unchanged.

## Investigation: shorten rail-status text safely (not yet enabled)
The source already has deterministic, selective compression:
- IR /train_state.json `title` -> affected segment and incident
  (delay, suspension, cancellation, possibility and recognized cause).
- JR West official English Hokuriku page -> Nanao-line section, type,
  timing and strong-wind/heavy-rain cause, ignoring unrelated lines.
- Unknown/retrieval failure must NEVER be labeled `normal`.
- Only route-relevant incident text is sent to the single-line LCD marquee.

Further formatting-only reductions seem viable: abbreviate
`遅延・見合わせの可能性` to `遅延/見合わせの恐れ`,
remove repeated "運行情報" prefixes and insert consistent delimiters.
Do not strip actual/possible distinction, affected segment, date or
"until" time. Today's official alerts include Nanao cancellations due
to high winds, with services stopping until about 17:00; the detailed
official notices distinguish individual trains and an IR segment that
may still operate despite Nanao cancellation. Careless summary would
mislead riders. No production text rewrite is introduced in this
version: separate review/tests are needed for each source pattern.

## CI
- Scheduler FPS, both control modes, absolute deadlines and edge cases
- New GUI input and validation, settings migration and live reload
- All prior official rail, USB, weather, layout and updater tests
- Windows frozen EXE build and offline update ZIP integration

Actual LCD throughput must be measured physically; fixed mode is a
requested update frequency, not a promise that the panel can reach it.
