import os
import struct
import subprocess
import sys
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from evdev import ecodes as e

from .samples import PenSample

# reMarkable 2 "Wacom I2C Digitizer" ranges (100 units per mm).
SENSOR_X_MAX = 20966
SENSOR_Y_MAX = 15725
SENSOR_PRESSURE_MAX = 4095
SENSOR_DISTANCE_MAX = 255
SENSOR_TILT_MAX = 9000

# struct input_event on the 32-bit ARM kernel: sec, usec, type, code, value.
EVENT = struct.Struct("<IIHHi")

# Finds the digitizer by name so the event number can change between firmwares.
REMOTE_COMMAND = (
    "for d in /sys/class/input/event*; do "
    'grep -qx "Wacom I2C Digitizer" "$d/device/name" && '
    'exec cat "/dev/input/${d##*/}"; '
    "done; echo 'digitizer not found' >&2; exit 1"
)


@dataclass(frozen=True)
class Event:
    time_s: float
    type: int
    code: int
    value: int


@dataclass
class PenState:
    abs: dict[int, int] = field(default_factory=dict)
    keys: dict[int, int] = field(default_factory=dict)
    dropped: bool = False


@dataclass(frozen=True)
class Mapping:
    rotate: int = 90
    aspect: float | None = 16 / 9

    def __post_init__(self):
        if self.rotate not in (0, 90, 180, 270):
            raise ValueError("rotate must be 0, 90, 180 or 270")
        if self.aspect is not None and not 0 < self.aspect < float("inf"):
            raise ValueError("aspect must be finite and positive")


def parse_events(buffer: bytes) -> tuple[list[Event], bytes]:
    end = len(buffer) - len(buffer) % EVENT.size
    events = [
        Event(sec + usec / 1e6, kind, code, value)
        for sec, usec, kind, code, value in EVENT.iter_unpack(buffer[:end])
    ]
    return events, buffer[end:]


def clamp(value, low=0.0, high=1.0):
    return min(high, max(low, value))


def crop(mapping: Mapping) -> tuple[float, float, float, float]:
    """Centered region of the rotated tablet, in normalized coordinates, matching the target aspect."""
    width, height = SENSOR_Y_MAX, SENSOR_X_MAX
    if mapping.rotate in (90, 270):
        width, height = height, width
    if mapping.aspect is None:
        return 0.0, 0.0, 1.0, 1.0
    if width / height > mapping.aspect:
        used = height * mapping.aspect / width
        return (1 - used) / 2, 0.0, (1 + used) / 2, 1.0
    used = width / mapping.aspect / height
    return 0.0, (1 - used) / 2, 1.0, (1 + used) / 2


def to_screen(
    sensor_x: int, sensor_y: int, tilt_x: int, tilt_y: int, mapping: Mapping
) -> tuple[float, float, float, float]:
    # Portrait, origin at the top-left of the display: sensor Y runs left to right
    # and sensor X runs bottom to top.
    u = sensor_y / SENSOR_Y_MAX
    v = 1 - sensor_x / SENSOR_X_MAX
    tu, tv = tilt_y / 100, -tilt_x / 100
    for _ in range(mapping.rotate // 90):
        u, v = 1 - v, u
        tu, tv = -tv, tu
    left, top, right, bottom = crop(mapping)
    x = clamp((u - left) / (right - left))
    y = clamp((v - top) / (bottom - top))
    return x, y, clamp(tu, -90, 90), clamp(tv, -90, 90)


def to_sample(state: PenState, time_s: float, mapping: Mapping) -> PenSample:
    keys, axes = state.keys, state.abs
    eraser = bool(keys.get(e.BTN_TOOL_RUBBER))
    in_proximity = eraser or bool(keys.get(e.BTN_TOOL_PEN))
    touching = in_proximity and bool(keys.get(e.BTN_TOUCH))
    x, y, tilt_x, tilt_y = to_screen(
        clamp(axes.get(e.ABS_X, 0), 0, SENSOR_X_MAX),
        clamp(axes.get(e.ABS_Y, 0), 0, SENSOR_Y_MAX),
        axes.get(e.ABS_TILT_X, 0),
        axes.get(e.ABS_TILT_Y, 0),
        mapping,
    )
    pressure = axes.get(e.ABS_PRESSURE, 0) / SENSOR_PRESSURE_MAX if touching else 0.0
    return PenSample(
        time_s=max(0.0, time_s),
        x=x,
        y=y,
        pressure=clamp(pressure),
        in_proximity=in_proximity,
        touching=touching,
        tilt_x=tilt_x,
        tilt_y=tilt_y,
        distance=clamp(axes.get(e.ABS_DISTANCE, 0) / SENSOR_DISTANCE_MAX),
        eraser=eraser,
        stylus=bool(keys.get(e.BTN_STYLUS)),
        stylus2=bool(keys.get(e.BTN_STYLUS2)),
    )


def decode(
    chunks: Iterable[bytes], mapping: Mapping, state: PenState | None = None
) -> Iterator[PenSample]:
    state = state or PenState()
    rest = b""
    for chunk in chunks:
        events, rest = parse_events(rest + chunk)
        for event in events:
            if event.type == e.EV_SYN:
                if event.code == e.SYN_DROPPED:
                    state.dropped = True
                elif event.code == e.SYN_REPORT:
                    # Events up to the report after a drop are incomplete; skip that frame.
                    if state.dropped:
                        state.dropped = False
                    else:
                        yield to_sample(state, event.time_s, mapping)
            elif not state.dropped:
                if event.type == e.EV_KEY:
                    state.keys[event.code] = event.value
                elif event.type == e.EV_ABS:
                    state.abs[event.code] = event.value


def read_chunks(stream) -> Iterator[bytes]:
    fd = stream.fileno()
    while chunk := os.read(fd, 4096):
        yield chunk


def ssh_command(host: str) -> list[str]:
    return [
        "ssh",
        "-T",
        "-o",
        "Compression=no",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "ServerAliveInterval=2",
        "-o",
        "ServerAliveCountMax=3",
        host,
        REMOTE_COMMAND,
    ]


def stream(host: str, mapping: Mapping, *, retry_s: float = 2.0) -> Iterator[PenSample]:
    """Yields pen samples forever, reconnecting when the tablet sleeps or the link drops."""
    while True:
        with subprocess.Popen(
            ssh_command(host), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE
        ) as process:
            print(f"Connecting to {host}.", flush=True)
            try:
                last = None
                for last in decode(read_chunks(process.stdout), mapping):
                    yield last
                # Lift the pen if the connection dropped mid-stroke.
                if last is not None and last.in_proximity:
                    yield PenSample(last.time_s, last.x, last.y, 0, False, False)
            finally:
                process.terminate()
        print(
            f"Connection to {host} ended (exit {process.returncode}), "
            f"retrying in {retry_s:g}s.",
            file=sys.stderr,
            flush=True,
        )
        time.sleep(retry_s)
