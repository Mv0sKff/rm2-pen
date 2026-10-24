import math
from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class PenSample:
    time_s: float
    x: float
    y: float
    pressure: float
    in_proximity: bool
    touching: bool
    tilt_x: float = 0.0
    tilt_y: float = 0.0
    distance: float = 0.0
    eraser: bool = False
    stylus: bool = False
    stylus2: bool = False

    def __post_init__(self):
        if not math.isfinite(self.time_s) or self.time_s < 0:
            raise ValueError("sample time must be finite and nonnegative")
        for name in ("x", "y", "pressure"):
            value = getattr(self, name)
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be in [0, 1]")
        for name in ("tilt_x", "tilt_y"):
            value = getattr(self, name)
            if not math.isfinite(value) or not -90 <= value <= 90:
                raise ValueError(f"{name} must be in [-90, 90] degrees")
        if not math.isfinite(self.distance) or not 0 <= self.distance <= 1:
            raise ValueError("distance must be in [0, 1]")
        if self.touching and not self.in_proximity:
            raise ValueError("contact requires proximity")
        if not self.touching and self.pressure != 0:
            raise ValueError("pressure requires contact")


@dataclass(frozen=True)
class DemoConfig:
    duration: float = 4.0
    rate: float = 120.0
    bounds: tuple[float, float, float, float] = (0.35, 0.35, 0.65, 0.65)
    aspect: float = 16 / 9
    pressure: float = 0.6

    def __post_init__(self):
        for name in ("duration", "rate", "aspect"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if not math.isfinite(self.pressure) or not 0 < self.pressure <= 1:
            raise ValueError("pressure must be in (0, 1]")
        if len(self.bounds) != 4 or any(
            not math.isfinite(v) or not 0 <= v <= 1 for v in self.bounds
        ):
            raise ValueError("bounds must contain four numbers in [0, 1]")
        left, top, right, bottom = self.bounds
        if left >= right or top >= bottom:
            raise ValueError("bounds must have left < right and top < bottom")


def demo_samples(shape: str, config: DemoConfig) -> Iterator[PenSample]:
    if shape not in {"square", "circle", "pressure"}:
        raise ValueError(f"unknown demo: {shape}")
    left, top, right, bottom = config.bounds
    cx, cy = (left + right) / 2, (top + bottom) / 2
    height = min(bottom - top, (right - left) * config.aspect)
    width = height / config.aspect
    count = max(4, math.ceil(config.duration * config.rate))
    # Include all four corners even when duration * rate is not divisible by four.
    if shape == "square":
        count = math.ceil(count / 4) * 4

    def point(t):
        if shape == "pressure":
            return left + (right - left) * t, cy
        if shape == "circle":
            angle = 2 * math.pi * (t % 1)
            return cx + width / 2 * math.cos(angle), cy + height / 2 * math.sin(angle)
        vertices = ((-1, -1), (1, -1), (1, 1), (-1, 1), (-1, -1))
        edge = min(3, int(t * 4))
        fraction = t * 4 - edge
        a, b = vertices[edge], vertices[edge + 1]
        return (
            cx + width / 2 * (a[0] + (b[0] - a[0]) * fraction),
            cy + height / 2 * (a[1] + (b[1] - a[1]) * fraction),
        )

    x, y = point(0)
    yield PenSample(0, x, y, 0, True, False)
    lead = 1 / config.rate
    for i in range(count + 1):
        t = i / count
        x, y = point(t)
        pressure = (
            0.1 + 0.9 * math.sin(math.pi * t) ** 2
            if shape == "pressure"
            else config.pressure
        )
        yield PenSample(lead + t * config.duration, x, y, pressure, True, True)
    end = lead + config.duration
    yield PenSample(end + lead, x, y, 0, True, False)
    yield PenSample(end + 2 * lead, x, y, 0, False, False)
