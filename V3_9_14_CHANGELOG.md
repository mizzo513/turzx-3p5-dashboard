# TURZX V3.9.14 — 10fps rail notice scroll

Based on V3.9.13 (10 GUI color presets and fixed-size tabs preserved).

## Changes
- Maximum desired rail notice scroll cadence is **10 frames per second**
  (100ms instead of 200ms). The scroll travel speed setting remains in
  pixels per second and defaults to 9.4px/s.
- No special suppression near clock second boundaries. An ongoing clock
  redraw can still take priority in the USB transmit branch, but the scroll
  scheduler no longer deliberately holds frames back for clock stability.
  This release does not attempt to resolve earlier second-display jitter.
- Idle event polling is 10ms instead of 20ms, reducing scheduling jitter.
- The existing adaptive serial-transfer backpressure is retained: a slow
  write can reduce the actual fps below 10, and optional intermediate
  frames are skipped rather than queued.
- The runtime status file now exposes
  `scroll_requested_fps` (10), `scroll_target_fps` (adaptive),
  `scroll_effective_fps_10s` (actual successful transfer count / 10s),
  and `scroll_transfer_ms` (most recent completed marquee USB write).
  Read at `%LOCALAPPDATA%\\TURZXDashboard\\runtime_status.json`.
- GUI help text reflects the new 10fps target.

## Is 10fps a hard limit?
No hard 10fps panel or firmware limit has been established.
Default notice region is approximately 315x17 pixels * 2 bytes/pixel =
10,710 bytes/frame. The uncompressed image payload is about
107kB/s at 10fps, 214kB/s at 20fps and 321kB/s at 30fps, plus
protocol overhead. The COM port is opened at a nominal 115200 baud, but
actual USB CDC/bridge transport behavior can differ. Do not claim
hardware FPS capacity from this baud number alone.
The current 9.4 pixels/second travel speed produces fewer than 10 distinct
whole-pixel positions each second. At a higher refresh rate, repeated pixel
positions may be sent; additional apparent smoothness requires either a
higher travel speed or subpixel/antialiasing techniques.

## Validation caveat
CI verifies scheduler timing and Windows frozen EXE/update workflows.
Only a physical panel and driver can confirm transfer throughput,
visible frame cadence and impact on the clock seconds.
