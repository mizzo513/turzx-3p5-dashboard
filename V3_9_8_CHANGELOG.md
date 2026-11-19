# TURZX V3.9.8 — smooth adaptive rail-status marquee

Based on V3.9.7. No change to display resolution, 180-degree rotation,
weather/rail data sources, text layout settings or USB automatic reconnect.

## Changes
- Rail-status scrolling changes from 16 pixels once per 1.7 seconds to a
  monotonic-time-based scroll targeting 5 frames per second (0.2-second cadence).
- Motion speed remains approximately 16/1.7 = 9.41 pixels per second;
  each normal frame advances approximately 1–2 pixels.
- The refresh cadence adapts down when measured USB notice-patch transfer
  duration approaches/exceeds the 200-ms target.
- Dropped frames do not accumulate a travel delay: the position always derives
  from elapsed monotonic time.
- The clock has priority. Optional marquee transfers are suppressed at clock
  updates and close to the next real-clock second boundary.
- A cached background is used for scroll-only changes; the USB transfer is
  limited to the existing one-line rail notice region, approximately 315x17 px
  with default user layout.
- Status diagnostics expose scroll transfer duration, adaptive frame target,
  frame counts and estimated clock packet delay.
- Existing automatic reconnect and the user-initiated reconnect button remain.
- Added automated tests for timing/frame skipping and pixel-exact marquee patch
  equivalence with the whole-screen renderer.

## Known limitations
- The application cannot interrupt an in-flight serial write. If the USB
  device is extremely slow, clock updates can still be delayed.
- Serial transfer telemetry measures the host-side write duration, not the
  panel's physical display refresh moment.
- Windows GUI and offline upgrade tests are performed in CI. Physical panel
  timing and any USB-driver-specific reconnect problems require testing
  on the connected TURZX device.
