import argparse
import math
import os
import sys
import time

from .samples import DemoConfig, demo_samples


def nonnegative(text):
    value = float(text)
    if not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError("expected a finite nonnegative number")
    return value


def bounds(text):
    try:
        values = tuple(float(value) for value in text.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected left,top,right,bottom") from error
    if len(values) != 4:
        raise argparse.ArgumentTypeError("expected left,top,right,bottom")
    return values


def aspect(text):
    if text == "none":
        return None
    try:
        width, _, height = text.partition(":")
        value = float(width) / float(height) if height else float(width)
    except (ValueError, ZeroDivisionError) as error:
        raise argparse.ArgumentTypeError("expected W:H, a number, or none") from error
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("expected a positive aspect ratio")
    return value


def parser():
    root = argparse.ArgumentParser(prog="rm2-pen")
    commands = root.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor")
    doctor.add_argument("--hold", type=nonnegative, default=0)
    demo = commands.add_parser("demo")
    demo.add_argument("shape", choices=("square", "circle", "pressure"))
    demo.add_argument("--delay", type=nonnegative, default=5)
    demo.add_argument("--duration", type=float, default=4)
    demo.add_argument("--rate", type=float, default=120)
    demo.add_argument("--bounds", type=bounds, default=(0.35, 0.35, 0.65, 0.65))
    demo.add_argument("--aspect", type=float, default=16 / 9)
    demo.add_argument("--pressure", type=float, default=0.6)
    run = commands.add_parser("run")
    run.add_argument("--host", default="remarkable")  # e.g root@ip
    run.add_argument("--rotate", type=int, choices=(0, 90, 180, 270), default=90)
    run.add_argument("--aspect", type=aspect, default=16 / 9)
    run.add_argument("--print", action="store_true", dest="print_only")
    return root


def run(args):
    from .remarkable import Mapping, stream

    samples = stream(args.host, Mapping(args.rotate, args.aspect))
    if args.print_only:
        for s in samples:
            print(
                f"x={s.x:.3f} y={s.y:.3f} p={s.pressure:.2f} "
                f"tilt={s.tilt_x:+.0f},{s.tilt_y:+.0f} d={s.distance:.2f} "
                f"{'eraser' if s.eraser else 'pen'}"
                f"{' touch' if s.touching else ''}"
                f"{'' if s.in_proximity else ' out'}",
                flush=True,
            )
        return 0
    from .tablet import create_device, forward

    with create_device() as device:
        node = device.device.path if device.device else "event node unavailable"
        print(f"Created {device.name}: {node}", flush=True)
        forward(device, samples)
    return 0


def main():
    args = parser().parse_args()
    try:
        if args.command == "run":
            return run(args)
        config = None
        if args.command == "demo":
            config = DemoConfig(
                args.duration, args.rate, args.bounds, args.aspect, args.pressure
            )
        else:
            for key in ("XDG_SESSION_TYPE", "XDG_CURRENT_DESKTOP", "WAYLAND_DISPLAY"):
                print(f"{key}={os.environ.get(key, '(unset)')}")
            print(f"/dev/uinput exists: {os.path.exists('/dev/uinput')}")
            print(f"/dev/uinput writable: {os.access('/dev/uinput', os.W_OK)}")
        from .tablet import create_device, play

        with create_device() as device:
            node = device.device.path if device.device else "event node unavailable"
            print(f"Created {device.name}: {node}", flush=True)
            if args.command == "doctor":
                print(
                    "Device creation passed. Verify libinput classification and Krita separately."
                )
                if args.hold:
                    print(
                        f"Holding device for {args.hold:g}s without pen motion.",
                        flush=True,
                    )
                    time.sleep(args.hold)
            else:
                assert config is not None
                print(
                    f"Drawing {args.shape} in {args.delay:g}s. Focus your Krita canvas.",
                    flush=True,
                )
                time.sleep(args.delay)
                play(device, demo_samples(args.shape, config))
                # Give consumers time to process the final pen-up before removal.
                time.sleep(0.1)
        return 0
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)
        return 130
    except ImportError as error:
        print(
            f"{error}. Install dependencies with: python -m pip install -e .",
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        if isinstance(error, OSError):
            print(
                "Check /dev/uinput and run scripts/setup-uinput.sh with sudo if needed.",
                file=sys.stderr,
            )
        return 1


if __name__ == "__main__":
    sys.exit(main())
