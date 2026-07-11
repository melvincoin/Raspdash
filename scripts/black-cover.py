#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import os
import signal
import sys
import time
from pathlib import Path


CW_OVERRIDE_REDIRECT = 1 << 9
EXPOSURE_MASK = 1 << 15


class XSetWindowAttributes(ctypes.Structure):
    _fields_ = [
        ("background_pixmap", ctypes.c_ulong),
        ("background_pixel", ctypes.c_ulong),
        ("border_pixmap", ctypes.c_ulong),
        ("border_pixel", ctypes.c_ulong),
        ("bit_gravity", ctypes.c_int),
        ("win_gravity", ctypes.c_int),
        ("backing_store", ctypes.c_int),
        ("backing_planes", ctypes.c_ulong),
        ("backing_pixel", ctypes.c_ulong),
        ("save_under", ctypes.c_int),
        ("event_mask", ctypes.c_long),
        ("do_not_propagate_mask", ctypes.c_long),
        ("override_redirect", ctypes.c_int),
        ("colormap", ctypes.c_ulong),
        ("cursor", ctypes.c_ulong),
    ]


def log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} black-cover: {message}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fullscreen black X11 cover for RaspDash kiosk startup.")
    parser.add_argument("--pid-file", default="/tmp/raspdash-cover.pid")
    parser.add_argument("--log", default="/tmp/raspdash-kiosk.log")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--raise-interval", type=float, default=0.25)
    args = parser.parse_args()

    pid_path = Path(args.pid_file)
    log_path = Path(args.log)
    pid_path.write_text(str(os.getpid()), encoding="ascii")

    running = True

    def stop(_signum: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    x11 = ctypes.cdll.LoadLibrary("libX11.so.6")
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XDefaultRootWindow.restype = ctypes.c_ulong
    x11.XBlackPixel.restype = ctypes.c_ulong
    x11.XCreateWindow.restype = ctypes.c_ulong

    display = x11.XOpenDisplay(None)
    if not display:
        log(log_path, "failed to open X display")
        return 1

    screen = x11.XDefaultScreen(display)
    root = x11.XDefaultRootWindow(display)
    width = x11.XDisplayWidth(display, screen)
    height = x11.XDisplayHeight(display, screen)
    black = x11.XBlackPixel(display, screen)

    attrs = XSetWindowAttributes()
    attrs.background_pixel = black
    attrs.border_pixel = black
    attrs.override_redirect = 1
    attrs.event_mask = EXPOSURE_MASK

    window = x11.XCreateWindow(
        display,
        root,
        0,
        0,
        width,
        height,
        0,
        0,
        1,
        0,
        CW_OVERRIDE_REDIRECT,
        ctypes.byref(attrs),
    )
    x11.XStoreName(display, window, b"RaspDash black cover")
    x11.XMapRaised(display, window)
    x11.XFlush(display)
    log(log_path, f"cover started pid={os.getpid()} window={window} size={width}x{height}")

    deadline = time.monotonic() + args.timeout
    try:
        while running and time.monotonic() < deadline:
            x11.XRaiseWindow(display, window)
            x11.XFlush(display)
            time.sleep(args.raise_interval)
        if running:
            log(log_path, "fallback timeout reached; removing cover")
    finally:
        x11.XDestroyWindow(display, window)
        x11.XCloseDisplay(display)
        try:
            pid_path.unlink()
        except OSError:
            pass
        log(log_path, "cover removed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
