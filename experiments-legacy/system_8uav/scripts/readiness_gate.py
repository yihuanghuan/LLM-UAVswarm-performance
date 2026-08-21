"""Pure readiness gate shared by experiment runners and unit tests."""

from dataclasses import dataclass
import math
import time


@dataclass(frozen=True)
class ReadySample:
    received_monotonic: float
    system_ready: bool
    armed: bool
    offboard: bool
    failsafe: bool
    altitude: float
    position_derived_speed: float


def sample_ready(sample, now, *, freshness_timeout, minimum_altitude,
                 speed_tolerance):
    return (
        sample is not None
        and now - sample.received_monotonic <= freshness_timeout
        and sample.system_ready
        and sample.armed
        and sample.offboard
        and not sample.failsafe
        and math.isfinite(sample.altitude)
        and sample.altitude >= minimum_altitude
        and math.isfinite(sample.position_derived_speed)
        and sample.position_derived_speed <= speed_tolerance
    )


class ContinuousReadinessGate:
    def __init__(self, uav_ids, *, freshness_timeout=0.5,
                 minimum_altitude=1.0, speed_tolerance=0.30,
                 hold_time=1.0):
        self.uav_ids = tuple(int(value) for value in uav_ids)
        self.freshness_timeout = float(freshness_timeout)
        self.minimum_altitude = float(minimum_altitude)
        self.speed_tolerance = float(speed_tolerance)
        self.hold_time = float(hold_time)
        self.samples = {}
        self.ready_since = None

    def update(self, uav_id, sample):
        self.samples[int(uav_id)] = sample

    def evaluate(self, now=None):
        now = time.monotonic() if now is None else float(now)
        ready = all(sample_ready(
            self.samples.get(uid), now,
            freshness_timeout=self.freshness_timeout,
            minimum_altitude=self.minimum_altitude,
            speed_tolerance=self.speed_tolerance,
        ) for uid in self.uav_ids)
        if not ready:
            self.ready_since = None
            return False
        if self.ready_since is None:
            self.ready_since = now
        return now - self.ready_since >= self.hold_time

    def diagnostics(self, now=None):
        now = time.monotonic() if now is None else float(now)
        return {
            str(uid): {
                "present": uid in self.samples,
                "age_s": (
                    None if uid not in self.samples else
                    now - self.samples[uid].received_monotonic
                ),
                **({} if uid not in self.samples else {
                    "system_ready": self.samples[uid].system_ready,
                    "armed": self.samples[uid].armed,
                    "offboard": self.samples[uid].offboard,
                    "failsafe": self.samples[uid].failsafe,
                    "altitude": self.samples[uid].altitude,
                    "position_derived_speed":
                        self.samples[uid].position_derived_speed,
                }),
            }
            for uid in self.uav_ids
        }
