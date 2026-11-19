# TURZX V3.9.7: clock stability and USB recovery

Changes from V3.9.6:

- The displayed clock continues to use the NTP-disciplined/PC-fallback clock (not a counter).
- The screen is redrawn only when actual content changes, avoiding a full in-memory redraw every 50 ms.
- Clock seconds are transmitted before an optional rail-information scroll step.
- Scroll steps are deferred near the next second boundary.
- Minute rollover transmits the date/time label area instead of a complete 480x320 frame.
- Disconnects trigger port closure and reconnection attempts. Each successful reconnect sends the orientation command and a complete frame.
- The settings GUI includes a "ディスプレイ再接続" button to request a port close/reopen without restarting the engine.
- The GUI reports the last USB connection error, and the runtime diagnostics record the last image transfer duration and kind.

USB recovery limitations:

If Windows registers the device but refuses to open its COM port even outside this application,
app-level retry cannot fix the USB driver. Close the app, use Windows Device Manager to
disable and re-enable only the matching TURZX USB serial device, then try again.
The app never performs a privileged Windows device reset on its own.

Hardware note: verified against the project's existing source and Windows CI tests;
live physical-device behavior needs validation on a connected Rev A TURZX panel.
