import time
from collections.abc import Iterable

from evdev import AbsInfo, UInput
from evdev import ecodes as e

from .samples import PenSample

NAME = "rm-wacom2 Virtual Pen"
X_MAX = 32767
Y_MAX = 32767
PRESSURE_MAX = 4095
DISTANCE_MAX = 255
# Tilt in hundredths of a degree; resolution is units per radian.
TILT_MAX = 9000
TILT_RESOLUTION = 5730


def create_device():
    return UInput(
        {
            e.EV_KEY: [
                e.BTN_TOOL_PEN,
                e.BTN_TOOL_RUBBER,
                e.BTN_TOUCH,
                e.BTN_STYLUS,
                e.BTN_STYLUS2,
            ],
            e.EV_ABS: [
                (e.ABS_X, AbsInfo(0, 0, X_MAX, 0, 0, 100)),
                (e.ABS_Y, AbsInfo(0, 0, Y_MAX, 0, 0, 100)),
                (e.ABS_PRESSURE, AbsInfo(0, 0, PRESSURE_MAX, 0, 0, 0)),
                (e.ABS_DISTANCE, AbsInfo(0, 0, DISTANCE_MAX, 0, 0, 0)),
                (
                    e.ABS_TILT_X,
                    AbsInfo(0, -TILT_MAX, TILT_MAX, 0, 0, TILT_RESOLUTION),
                ),
                (
                    e.ABS_TILT_Y,
                    AbsInfo(0, -TILT_MAX, TILT_MAX, 0, 0, TILT_RESOLUTION),
                ),
            ],
        },
        name=NAME,
        vendor=0,
        product=0x0002,
        version=1,
        bustype=e.BUS_VIRTUAL,
        phys="rm-wacom2/pen0",
        input_props=[e.INPUT_PROP_POINTER],
    )


def emit(device, sample: PenSample):
    # BTN_TOUCH must be first in a contact frame for legacy input compatibility.
    device.write(e.EV_KEY, e.BTN_TOUCH, int(sample.touching))
    device.write(
        e.EV_KEY, e.BTN_TOOL_PEN, int(sample.in_proximity and not sample.eraser)
    )
    device.write(
        e.EV_KEY, e.BTN_TOOL_RUBBER, int(sample.in_proximity and sample.eraser)
    )
    device.write(e.EV_KEY, e.BTN_STYLUS, int(sample.stylus))
    device.write(e.EV_KEY, e.BTN_STYLUS2, int(sample.stylus2))
    device.write(e.EV_ABS, e.ABS_X, round(sample.x * X_MAX))
    device.write(e.EV_ABS, e.ABS_Y, round(sample.y * Y_MAX))
    device.write(e.EV_ABS, e.ABS_PRESSURE, round(sample.pressure * PRESSURE_MAX))
    device.write(e.EV_ABS, e.ABS_DISTANCE, round(sample.distance * DISTANCE_MAX))
    device.write(e.EV_ABS, e.ABS_TILT_X, round(sample.tilt_x * 100))
    device.write(e.EV_ABS, e.ABS_TILT_Y, round(sample.tilt_y * 100))
    device.syn()


def release(device):
    device.write(e.EV_KEY, e.BTN_TOUCH, 0)
    device.write(e.EV_ABS, e.ABS_PRESSURE, 0)
    device.write(e.EV_KEY, e.BTN_STYLUS, 0)
    device.write(e.EV_KEY, e.BTN_STYLUS2, 0)
    device.write(e.EV_KEY, e.BTN_TOOL_PEN, 0)
    device.write(e.EV_KEY, e.BTN_TOOL_RUBBER, 0)
    device.syn()


def forward(device, samples: Iterable[PenSample]):
    try:
        for sample in samples:
            emit(device, sample)
    finally:
        release(device)


def play(
    device, samples: Iterable[PenSample], *, clock=time.monotonic, sleep=time.sleep
):
    start = clock()
    previous = -1.0
    try:
        for sample in samples:
            if sample.time_s < previous:
                raise ValueError("sample timestamps must be nondecreasing")
            previous = sample.time_s
            remaining = start + sample.time_s - clock()
            if remaining > 0:
                sleep(remaining)
            emit(device, sample)
    finally:
        release(device)
