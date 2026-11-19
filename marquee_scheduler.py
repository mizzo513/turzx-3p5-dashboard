# SPDX-License-Identifier: GPL-3.0-or-later
"""Real-time, best-effort rail notice marquee scheduling.

The marquee never controls the clock. Frames are computed from monotonic elapsed
time, so dropping optional USB transfers cannot slow down scroll travel.
"""
from dataclasses import dataclass


@dataclass
class MarqueeScheduler:
    pixels_per_second: float = 9.4  # configurable via rail_scroll_speed_px_s
    target_fps: float = 5.0
    pause_seconds: float = 2.0
    started_at: float | None = None
    next_frame_at: float = 0.0
    transfer_ema_s: float = 0.0
    sent_frames: int = 0
    skipped_frames: int = 0

    def reset(self, tick: float):
        self.started_at = tick + self.pause_seconds
        self.next_frame_at = self.started_at + 1.0 / self.target_fps
        self.transfer_ema_s = 0.0
        self.sent_frames = 0
        self.skipped_frames = 0

    def disable(self):
        self.started_at = None
        self.next_frame_at = 0.0

    @property
    def interval(self):
        # 5 fps when possible; lower the transfer frequency if the USB port
        # cannot drain a 315x17 RGB565 patch quickly enough.
        minimum = 1.0 / self.target_fps
        return max(minimum, min(0.8, self.transfer_ema_s * 1.5))

    def candidate(self, tick: float, displayed_px: int, *, clock_due: bool,
                  second_fraction: float):
        """Return target pixel offset or None; suppressed frames are dropped."""
        if self.started_at is None or tick + 1e-9 < self.next_frame_at:
            return None
        if tick < self.started_at:
            return None
        self.next_frame_at = tick + self.interval
        offset = int((tick - self.started_at) * self.pixels_per_second)
        if offset == displayed_px:
            return None
        # Noninterruptible COM writes must not be started just before the
        # next second. The estimated transfer time is included in the margin.
        safety_margin = max(0.12, self.transfer_ema_s * 1.3 + 0.06)
        if clock_due or 1.0 - second_fraction <= safety_margin:
            self.skipped_frames += 1
            return None
        return offset

    def record_transfer(self, duration_s: float):
        duration_s = max(0.0, float(duration_s))
        if not self.sent_frames:
            self.transfer_ema_s = duration_s
        else:
            self.transfer_ema_s = (self.transfer_ema_s * 0.75 +
                                   duration_s * 0.25)
        self.sent_frames += 1
