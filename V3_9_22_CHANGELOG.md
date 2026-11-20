# TURZX V3.9.22 — transfer platform / waiting time separator

- The transfer-platform label in the three displayed connection rows now
  uses a Japanese full-width space (U+3000) instead of the slash:
  - before: `3→6/12分`
  - after:  `3→6　12分`
- Applies to all via-Kanazawa journeys with a transfer and any number of
  minutes; no change to `直通` for through journeys or to single-leg modes.
- No other LCD geometry, editable text keys, font sizes, colors or train
  status-fetch behavior is changed.
- Update the train-specific status and variable-width transfer-time
  regression tests to require the exact new separator.
- Standard Windows build, GUI tests, EXE startup and updater integration.
