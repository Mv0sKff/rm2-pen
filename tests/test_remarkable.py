import unittest

from evdev import ecodes as e

from rm_wacom2.remarkable import (
    EVENT,
    SENSOR_X_MAX,
    SENSOR_Y_MAX,
    Mapping,
    crop,
    decode,
    parse_events,
    to_screen,
)


def pack(*events, sec=100, usec=0):
    return b"".join(EVENT.pack(sec, usec, *event) for event in events)


def frame(x, y, *extra):
    return pack(
        (e.EV_ABS, e.ABS_X, x), (e.EV_ABS, e.ABS_Y, y), *extra, (e.EV_SYN, 0, 0)
    )


PORTRAIT = Mapping(rotate=0, aspect=None)


class ParseTests(unittest.TestCase):
    def test_partial_event_is_kept(self):
        data = pack((e.EV_ABS, e.ABS_X, 7), usec=500000)
        events, rest = parse_events(data + data[:5])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].value, 7)
        self.assertAlmostEqual(events[0].time_s, 100.5)
        self.assertEqual(rest, data[:5])

    def test_decode_across_chunk_boundaries(self):
        data = frame(100, 200, (e.EV_KEY, e.BTN_TOOL_PEN, 1))
        chunks = [data[i : i + 3] for i in range(0, len(data), 3)]
        samples = list(decode(chunks, PORTRAIT))
        self.assertEqual(len(samples), 1)
        self.assertTrue(samples[0].in_proximity)
        self.assertFalse(samples[0].touching)

    def test_touch_pressure_eraser(self):
        data = frame(
            0,
            0,
            (e.EV_KEY, e.BTN_TOOL_RUBBER, 1),
            (e.EV_KEY, e.BTN_TOUCH, 1),
            (e.EV_ABS, e.ABS_PRESSURE, 4095),
        ) + pack((e.EV_KEY, e.BTN_TOUCH, 0), (e.EV_SYN, 0, 0))
        down, up = decode([data], PORTRAIT)
        self.assertTrue(down.eraser and down.touching)
        self.assertEqual(down.pressure, 1)
        # Stale pressure without contact must not leak into the sample.
        self.assertFalse(up.touching)
        self.assertEqual(up.pressure, 0)

    def test_dropped_frame_is_skipped(self):
        data = (
            pack((e.EV_ABS, e.ABS_X, 1), (e.EV_SYN, e.SYN_DROPPED, 0))
            + pack((e.EV_ABS, e.ABS_X, 2), (e.EV_SYN, 0, 0))
            + frame(3, 3, (e.EV_KEY, e.BTN_TOOL_PEN, 1))
        )
        self.assertEqual(len(list(decode([data], PORTRAIT))), 1)


class MappingTests(unittest.TestCase):
    def test_portrait_corners(self):
        top_left = to_screen(SENSOR_X_MAX, 0, 0, 0, PORTRAIT)
        bottom_right = to_screen(0, SENSOR_Y_MAX, 0, 0, PORTRAIT)
        self.assertEqual(top_left[:2], (0, 0))
        self.assertEqual(bottom_right[:2], (1, 1))

    def test_rotations_move_portrait_top_left(self):
        expected = {0: (0, 0), 90: (1, 0), 180: (1, 1), 270: (0, 1)}
        for rotate, corner in expected.items():
            with self.subTest(rotate=rotate):
                mapping = Mapping(rotate=rotate, aspect=None)
                self.assertEqual(to_screen(SENSOR_X_MAX, 0, 0, 0, mapping)[:2], corner)

    def test_tilt_rotates_with_position(self):
        # Pen leaning toward portrait right (sensor +Y) leans toward screen bottom at 90.
        _, _, tx, ty = to_screen(0, 0, 0, 3000, Mapping(rotate=90, aspect=None))
        self.assertEqual((round(tx), round(ty)), (0, 30))

    def test_crop_matches_aspect(self):
        for rotate in (0, 90):
            for aspect in (16 / 9, 1, 9 / 16):
                with self.subTest(rotate=rotate, aspect=aspect):
                    left, top, right, bottom = crop(Mapping(rotate, aspect))
                    width, height = SENSOR_Y_MAX, SENSOR_X_MAX
                    if rotate == 90:
                        width, height = height, width
                    used = (right - left) * width / ((bottom - top) * height)
                    self.assertAlmostEqual(used, aspect)
                    self.assertTrue(right - left == 1 or bottom - top == 1)


if __name__ == "__main__":
    unittest.main()
