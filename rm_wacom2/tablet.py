import time
from collections.abc import Iterable

from evdev import AbsInfo, UInput
from evdev import ecodes as e

from .samples import PenSample

NAME = "rm-wacom2 Virtual Pen"
X_MAX = 32767
Y_MAX = 32767
PRESSURE_MAX = 4095


def create_device():
    return UInput(
        {
            e.EV_KEY: [e.BTN_TOOL_PEN, e.BTN_TOUCH],
            e.EV_ABS: [
                (e.ABS_X, AbsInfo(0, 0, X_MAX, 0, 0, 100)),
                (e.ABS_Y, AbsInfo(0, 0, Y_MAX, 0, 0, 100)),
                (e.ABS_PRESSURE, AbsInfo(0, 0, PRESSURE_MAX, 0, 0, 0)),
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
    device.write(e.EV_KEY, e.BTN_TOOL_PEN, int(sample.in_proximity))
    device.write(e.EV_ABS, e.ABS_X, round(sample.x * X_MAX))
    device.write(e.EV_ABS, e.ABS_Y, round(sample.y * Y_MAX))
    device.write(e.EV_ABS, e.ABS_PRESSURE, round(sample.pressure * PRESSURE_MAX))
    device.syn()


def release(device):
    device.write(e.EV_KEY, e.BTN_TOUCH, 0)
    device.write(e.EV_ABS, e.ABS_PRESSURE, 0)
    device.write(e.EV_KEY, e.BTN_TOOL_PEN, 0)
    device.syn()


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
