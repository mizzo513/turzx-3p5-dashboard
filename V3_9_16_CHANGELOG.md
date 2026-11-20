# TURZX V3.9.16 — adaptive pixel-difference USB patches

Built on V3.9.15. The LCD appearance, 10fps target, 10 settings palettes,
train/weather data and USB recovery features are unchanged.

## USB notice transfer optimization
- Render the previous and next visible rail-status text using exactly the
  same font, color, x/y, clip rectangle, gap and scrolling offsets as the
  existing whole-screen renderer.
- Compute a pixel-exact RGB difference between those two rendered notice
  strips. Transfer only the smallest bounding rectangle that contains all
  *changed* pixels, including pixels erased at the previous text position.
- Adjusts width and height automatically to text size, visible glyphs,
  scrolling position and user-customized settings. A fixed 315x17 transfer
  area is no longer needed for ordinary marquee-only updates.
- The **visual clip/position remains unchanged**, as does the 180-degree
  rotation protocol. A very wide marquee may still alter almost every
  horizontal pixel of the viewport: no unsupported speedup is promised.
- If no visible pixel changes, skip USB transfer while retaining the correct
  software scroll offset. Keep adaptive 10fps scheduling and serial fault
  recovery.
- The code composes only the small notice crop instead of duplicating the
  full 480x320 frame for each scroll-only transfer.

## Live status additions (local STATUS IPC)
- `scroll_transfer_width_px` and `scroll_transfer_height_px`:
  most recent sent marquee rectangle's actual dimensions
- `scroll_transfer_bytes`: last marquee RGB565 payload bytes
- `scroll_transfer_original_bytes`: bytes required by the full notice clip
  at the same font/custom layout
- `scroll_transfer_reduction_pct`: saved pixels relative to that clip
- Previous `scroll_transfer_ms`, `scroll_requested_fps`,
  `scroll_target_fps`, `scroll_effective_fps_10s` remain.

No disk runtime_status.json is created; use the localhost-only STATUS
command as previously documented.

## Testing
- Pixel-by-pixel screen reconstruction with previous frame + new USB patch
  equals full-frame renderer at many offsets, including wraps and skipped
  positions (ghost-free)
- Font sizes from 8 to 32, custom train panel colors, notice positioning,
  custom text color and the unchanged appearance of static messages
- Existing regression tests and Windows EXE / update ZIP integration
- Physical TURZX throughput requires real USB measurement: patch dimensions
  may shrink without a proportional reduction in transfer time, depending
  on fixed transport overhead.
