# TURZX V3.9.18 — optional concise rail-operation text

## New settings
- A new checkbox under the "乗換" tab:
  運行情報の文章を要約する（ON＝短縮 / OFF＝従来表示）
- Default OFF: existing installations keep the exact V3.9.17 LCD text.
- ON: fixed, conservative Japanese abbreviations applied to the already
  officially parsed IR and JR West line notice:
  - 遅延・見合わせの可能性 → 遅延/見合わせの恐れ
  - 運転見合わせの可能性 → 見合わせの恐れ
  - 運休の可能性 → 運休の恐れ
  - 運転見合わせ → 見合わせ
  - Padded separators → compact separators
- Preserve confirmed vs potential disruptions, dates, reasons, train
  route sections and status of unavailable sources. Unrecognized text stays
  unchanged; no free-form generated summary is used.
- Both ON and OFF keep using the existing 5-minute official-source update
  and single-line notice marquee, with 1–30fps fixed/adaptive settings.
- Applies on "設定を即時反映" without restart. When changed, the display
  signature causes the LCD to repaint so obsolete glyphs are cleared.
- Local STATUS IPC preserves `rail_status` as the original parsed text and
  adds `rail_status_display` and `rail_status_summarize` for comparison.
- Version labels, layouts, theme presets, the 10fps default and current
  USB reconnect/partial RGB565 transfers are unchanged.

## Intentional limitations
- OFF means the existing V3.9.17 *already source-parsed* text, not the
  complete official website news article.
- The ON transformation is intentionally limited: longer route-specific
  messages that cannot be safely shortened may remain the same length.
- The device LCD still reports an official-source summary, not a guarantee
  of a particular departing train running normally.
- Official railway sources retain their existing independent failure
  states. No unknown status is converted to "normal".

## Tests
- ON/OFF string equivalence and official parser fixtures
- Preserve timing / possible vs confirmed / affected segments
- Render updates contained in the intended notice band
- Old setting files remain opted-out and live reload supports ON
- Existing GUI, USB, weather and updater regression tests
