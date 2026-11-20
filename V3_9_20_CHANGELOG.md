# TURZX V3.9.20 — NTP → HTTPS → PC automatic clock failover

## What changed

- Keep the existing NICT/custom-server NTP UDP/123 synchronization as
  **first choice** (2.5-second request timeout).
- If NTP fails, query the HTTPS time service previously tested
  successfully by the user:
  `https://timeapi.io/api/Time/current/zone?timeZone=Asia/Tokyo`.
  Use HTTPS/TCP 443 with a 5-second request timeout. Server time comes
  from JSON `dateTime`, not from OCR or a browser clock.
- Validate the service timezone (`Asia/Tokyo`), RFC3339/ISO timestamp,
  sanity of year and response size. No invalid response becomes clock time.
- Approximate one-way latency by half the observed monotonic round-trip
  duration, add to the server time and anchor the result to the existing
  `time.monotonic()` timebase, without updating the Windows system clock.
  The RTT/2 number is a rough uncertainty indicator, not a guaranteed
  absolute accuracy or equivalence to NTP.
- If both external sources fail, use the PC time; retain the last
  accepted external sample until its usual 6-hour expiration.
- Preserve normal 30-minute automatic synchronization (user-configurable
  5–1440 min). Continue to retry NTP on later cycles, regardless of
  whether the previous attempt used HTTPS; no permanent lock-in.
- The existing manual sync IPC and button now request the same NTP-first
  HTTPS-fallback process and ignore the configured interval.
- The "表示・時計" tab explains the priority and clearly reports a manual
  successful source [NTP] or [HTTPS], or errors from both sources.
- Runtime STATUS now exposes `time_source` (NTP / HTTPS / PC),
  `time_sync_rtt_ms`, `time_estimated_error_ms`, `ntp_error`
  (NTP timeout even if HTTPS succeeds), and `ntp_manual_source`.
  No disk runtime_status.json file is created.

## Scope retained
- Existing weather and train APIs, official IR/JR rail-status summary
  toggle, numeric fixed/adaptive marquee FPS, region delta USB updates,
  NTP server name configuration and LCD layout remain unchanged.
- A non-NTP time service is a third-party dependency. It may be
  unavailable or rate-limit callers; the app never claims the website's
  clock is precisely synchronized to NTP. The default 30-minute refresh
  uses at most ~48 HTTPS time requests/day when NTP always fails.
- No API key is required for the demonstrated HTTPS endpoint, although
  third-party service policies can change.

## Tests
- Mock the known good TimeAPI.io JSON shape, 7-digit fractional seconds,
  timezone validation, invalid/missing fields and oversized responses.
- Verify NTP priority and no HTTPS call when NTP succeeds.
- Verify NTP timeout leads to HTTPS and monotonic clock time advances.
- Verify dual failure reports PC and preserves active external sample
  for up to 6 hours.
- Windows settings GUI source-specific feedback, existing IPC,
  USB recovery, weather/rail tests, EXE startup and updater integration.
