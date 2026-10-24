# rm-wacom2

Use a reMarkable 2 as a pen tablet on a Linux PC. Pen events are streamed over SSH from the tablet's digitizer and replayed through a virtual uinput tablet, so desktop apps get position, pressure, tilt, hover and eraser.

Nothing is installed on the tablet; it only needs SSH access as root.

## Setup

```sh
python -m pip install -e .
sudo sh scripts/setup-uinput.sh "$USER"   # then log out and back in
```

`ssh remarkable` should log in without a password prompt (key auth, `~/.ssh/config` host entry, or Tailscale SSH). Over USB the tablet is at `root@10.11.99.1`.

## Usage

```sh
rm-wacom2 run                       # landscape, mapped to a 16:9 area
rm-wacom2 run --rotate 0 --aspect none
rm-wacom2 run --host root@10.11.99.1
rm-wacom2 run --print               # show converted samples, no device
```

- `--rotate` turns the tablet clockwise (0 is portrait).
- `--aspect` is the target monitor shape (`16:9`, `1.6`, or `none` for the whole surface); the largest centered tablet area with that shape is used.
- Map the virtual tablet to a monitor in your desktop's tablet settings.

The connection reconnects automatically when the tablet sleeps. Strokes also land in the notebook open on the tablet, so keep a scratch page open.

## Diagnostics

```sh
rm-wacom2 doctor          # check uinput access and device creation
rm-wacom2 demo circle     # draw a synthetic stroke
python -m unittest tests/test_tablet.py tests/test_remarkable.py
```
