import unittest
from dataclasses import replace

from evdev import ecodes as e

from rm_wacom2.samples import DemoConfig, PenSample, demo_samples
from rm_wacom2.tablet import PRESSURE_MAX, emit, play


class RecordingDevice:
    def __init__(self):
        self.frames = []
        self.pending = []

    def write(self, event_type, code, value):
        self.pending.append((event_type, code, value))

    def syn(self):
        self.frames.append(self.pending)
        self.pending = []


class SamplesTests(unittest.TestCase):
    def test_invalid_samples(self):
        valid = PenSample(
            time_s=0, x=0.5, y=0.5, pressure=0, in_proximity=True, touching=False
        )
        for update in (
            {"time_s": -1},
            {"time_s": float("inf")},
            {"x": float("nan")},
            {"y": 1.01},
            {"pressure": 0.2},
            {"touching": True, "in_proximity": False},
        ):
            with self.subTest(update=update), self.assertRaises(ValueError):
                replace(valid, **update)

    def test_invalid_config(self):
        for update in (
            {"duration": 0},
            {"rate": float("inf")},
            {"aspect": -1},
            {"pressure": float("nan")},
            {"bounds": (0.8, 0.1, 0.2, 0.9)},
        ):
            with self.subTest(update=update), self.assertRaises(ValueError):
                replace(DemoConfig(), **update)

    def test_geometry_and_transitions(self):
        for aspect in (0.5625, 1, 16 / 9, 32 / 9):
            for shape in ("square", "circle"):
                with self.subTest(aspect=aspect, shape=shape):
                    config = DemoConfig(aspect=aspect)
                    samples = list(demo_samples(shape, config))
                    contact = [s for s in samples if s.touching]
                    self.assertEqual(
                        (contact[0].x, contact[0].y), (contact[-1].x, contact[-1].y)
                    )
                    width = max(s.x for s in contact) - min(s.x for s in contact)
                    height = max(s.y for s in contact) - min(s.y for s in contact)
                    self.assertAlmostEqual(width * aspect, height)
                    for s in samples:
                        self.assertTrue(0.35 <= s.x <= 0.65)
                        self.assertTrue(0.35 <= s.y <= 0.65)
                    self.assertFalse(samples[0].touching)
                    self.assertTrue(samples[0].in_proximity)
                    self.assertFalse(samples[-2].touching)
                    self.assertTrue(samples[-2].in_proximity)
                    self.assertFalse(samples[-1].in_proximity)
                    self.assertEqual(
                        sorted(s.time_s for s in samples), [s.time_s for s in samples]
                    )

    def test_square_includes_corners_at_nonintegral_rate(self):
        contact = [
            s
            for s in demo_samples("square", DemoConfig(duration=1.1, rate=13, aspect=1))
            if s.touching
        ]
        for corner in ((0.35, 0.35), (0.65, 0.35), (0.65, 0.65), (0.35, 0.65)):
            self.assertIn(corner, [(s.x, s.y) for s in contact])

    def test_pressure_ramp(self):
        contact = [s for s in demo_samples("pressure", DemoConfig()) if s.touching]
        self.assertAlmostEqual(contact[0].pressure, 0.1)
        self.assertAlmostEqual(contact[-1].pressure, 0.1)
        self.assertAlmostEqual(contact[len(contact) // 2].pressure, 1)
        self.assertEqual(len({s.y for s in contact}), 1)


class BackendTests(unittest.TestCase):
    def test_frame_and_axis_conversion(self):
        device = RecordingDevice()
        emit(device, PenSample(0, 0, 1, 1, True, True))
        self.assertEqual(
            device.frames[0],
            [
                (e.EV_KEY, e.BTN_TOUCH, 1),
                (e.EV_KEY, e.BTN_TOOL_PEN, 1),
                (e.EV_ABS, e.ABS_X, 0),
                (e.EV_ABS, e.ABS_Y, 32767),
                (e.EV_ABS, e.ABS_PRESSURE, PRESSURE_MAX),
            ],
        )

    def test_cleanup_on_interruption_and_source_error(self):
        for error in (KeyboardInterrupt, RuntimeError):
            device = RecordingDevice()

            def interrupted(error=error):
                yield PenSample(0, 0.5, 0.5, 0.5, True, True)
                raise error()

            with self.assertRaises(error):
                play(device, interrupted())
            self.assertEqual(
                device.frames[-1],
                [
                    (e.EV_KEY, e.BTN_TOUCH, 0),
                    (e.EV_ABS, e.ABS_PRESSURE, 0),
                    (e.EV_KEY, e.BTN_TOOL_PEN, 0),
                ],
            )

    def test_absolute_deadlines(self):
        now = [10.0]
        waits = []

        def sleep(delay):
            waits.append(delay)
            now[0] += delay + 0.05

        samples = [PenSample(t, 0.5, 0.5, 0, True, False) for t in (0, 1, 2)]
        play(RecordingDevice(), samples, clock=lambda: now[0], sleep=sleep)
        self.assertAlmostEqual(waits[0], 1)
        self.assertAlmostEqual(waits[1], 0.95)

    def test_backwards_time_releases_contact(self):
        device = RecordingDevice()
        samples = [PenSample(t, 0.5, 0.5, 0.5, True, True) for t in (1, 0)]
        with self.assertRaises(ValueError):
            play(device, samples, clock=lambda: 0, sleep=lambda _: None)
        self.assertIn((e.EV_KEY, e.BTN_TOUCH, 0), device.frames[-1])


if __name__ == "__main__":
    unittest.main()
