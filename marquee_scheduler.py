# SPDX-License-Identifier: GPL-3.0-or-later
"""Real-time, best-effort rail notice marquee scheduling.

The marquee never controls the clock. Frames are computed from monotonic elapsed
time, so dropping optional USB transfers cannot slow down scroll travel.
"""
from dataclasses import dataclass


@dataclass
class MarqueeScheduler:
    pixels_per_second: float = 9.4  # configurable via rail_scroll_speed_px_s
    target_fps: float = 10.0  # user-requested cap; 1..30 frames/second
    fps_mode: str = 'adaptive'  # adaptive (transfer-time aware) or fixed
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
        """Requested cadence, or slower if recent USB-frame writes need it.

        Fixed mode does not artificially delay frames for estimated transfer
        cost. Since the serial sender is synchronous, real USB throughput
        still limits actual FPS. Neither mode queues outdated frames.
        """
        minimum = 1.0 / self.target_fps
        if self.fps_mode == 'fixed':
            return minimum
        # Keep the established safety factor for the adaptive option.
        return max(minimum, min(0.8, self.transfer_ema_s * 1.5))

    def candidate(self, tick: float, displayed_px: int, *, clock_due: bool,
                  second_fraction: float):
        """Return target pixel offset or None; suppressed frames are dropped."""
        if self.started_at is None or tick + 1e-9 < self.next_frame_at:
            return None
        if tick < self.started_at:
            return None
        # Advance the periodic deadline from the previous target time,
        # not from the time this iteration happened to run. This avoids
        # accumulating 5–15 ms of polling drift on every frame. If USB
        # transfers were slow, discard missed deadlines rather than queue
        # stale frames. The next pixel position still derives from elapsed
        # monotonic time.
        interval=self.interval
        due=self.next_frame_at
        missed=max(1,int((tick-due+1e-9)//interval)+1)
        self.next_frame_at=due+missed*interval
        offset = int((tick - self.started_at) * self.pixels_per_second + 1e-7)
        if offset == displayed_px:
            return None
        # The clock has no reserved time window in V3.9.14: the caller may
        # still send an existing clock update first, but seconds never cause
        # the marquee scheduler to suppress a candidate.
        return offset

    def record_transfer(self, duration_s: float):
        duration_s = max(0.0, float(duration_s))
        if not self.sent_frames:
            self.transfer_ema_s = duration_s
        else:
            self.transfer_ema_s = (self.transfer_ema_s * 0.75 +
                                   duration_s * 0.25)
        self.sent_frames += 1
