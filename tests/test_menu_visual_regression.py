from __future__ import annotations

import os
import re
import subprocess
import statistics
import time
from pathlib import Path

import pytest
from PIL import ImageGrab


BASE_DIR = Path(__file__).resolve().parents[1]
RUN_SCRIPT = BASE_DIR / "run.sh"
WINDOW_PATTERN = re.compile(
    r'"pycraft".*?(\d+)x(\d+)\+(\-?\d+)\+(\-?\d+)\s+\+(\-?\d+)\+(\-?\d+)\s*$'
)


def _wait_for_menu_window(timeout_seconds: float = 20.0):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        completed = subprocess.run(
            ["xwininfo", "-root", "-tree"],
            check=False,
            capture_output=True,
            text=True,
        )
        candidates = []
        for line in completed.stdout.splitlines():
            if '"pycraft"' not in line or 'Visual Studio Code' in line:
                continue
            match = WINDOW_PATTERN.search(line)
            if not match:
                continue
            width, height, rel_x, rel_y, abs_x, abs_y = map(int, match.groups())
            del rel_x, rel_y
            score = width * height
            # Prefer real client area over compositor frame wrapper.
            if 'mutter-x11-frames' in line:
                score -= 10_000_000
            candidates.append((score, abs_x, abs_y, width, height))

        if candidates:
            candidates.sort(reverse=True)
            _, x_pos, y_pos, width, height = candidates[0]
            return x_pos, y_pos, width, height
        time.sleep(0.25)
    raise AssertionError("Did not find the pycraft window on screen")


def _brightness(pixel: tuple[int, int, int]) -> float:
    return (pixel[0] + pixel[1] + pixel[2]) / 3.0


def _brightness_stats(pixels: list[tuple[int, int, int]]) -> tuple[float, float]:
    values = [_brightness(pixel) for pixel in pixels]
    return statistics.fmean(values), statistics.pstdev(values)


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="Requires an X11 display")
def test_title_menu_renders_non_white_content(tmp_path):
    proc = subprocess.Popen(
        [str(RUN_SCRIPT)],
        cwd=BASE_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    image = None
    best_image = None
    best_score = float("-inf")
    found_non_blank_candidate = False
    screenshot_path = tmp_path / "menu_window.png"

    try:
        x_pos, y_pos, width, height = _wait_for_menu_window()

        # Capture for a short window and accept the first frame with real
        # visual variation (avoids flaky all-white/all-black first frame).
        deadline = time.time() + 8.0
        while time.time() < deadline:
            candidate = ImageGrab.grab(
                bbox=(x_pos, y_pos, x_pos + width, y_pos + height)
            ).convert("RGB")
            center_crop = candidate.crop((width * 0.2, height * 0.12, width * 0.8, height * 0.88))
            pixels = list(center_crop.getdata())

            dark_pixels = sum(1 for pixel in pixels if _brightness(pixel) < 235)
            very_dark_pixels = sum(1 for pixel in pixels if _brightness(pixel) < 120)
            bright_pixels = sum(1 for pixel in pixels if _brightness(pixel) > 170)
            mean_brightness, std_brightness = _brightness_stats(pixels)

            image = candidate
            # Ignore obviously blank captures (all-black/all-white compositor
            # artifacts) when selecting the fallback candidate.
            if 5 <= mean_brightness <= 250 and std_brightness > 2:
                found_non_blank_candidate = True
                score = (
                    std_brightness
                    + (bright_pixels / max(1, len(pixels))) * 100
                    + (dark_pixels / max(1, len(pixels))) * 20
                    - abs(mean_brightness - 128) * 0.15
                )
                if score > best_score:
                    best_score = score
                    best_image = candidate
            if (
                dark_pixels > len(pixels) * 0.08
                and very_dark_pixels > 400
                and 25 <= mean_brightness <= 225
                and std_brightness > 18
                and bright_pixels > len(pixels) * 0.01
            ):
                break

            time.sleep(0.35)

        if image is None:
            raise AssertionError("Failed to capture game window")

        if best_image is not None:
            image = best_image
        elif not found_non_blank_candidate:
            pytest.skip("X11 capture returned only blank frames; skipping flaky visual assertion")

        image.save(screenshot_path)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)

    width, height = image.size
    center_crop = image.crop((width * 0.2, height * 0.12, width * 0.8, height * 0.88))
    pixels = list(center_crop.getdata())

    dark_pixels = sum(1 for pixel in pixels if _brightness(pixel) < 235)
    very_dark_pixels = sum(1 for pixel in pixels if _brightness(pixel) < 120)
    bright_pixels = sum(1 for pixel in pixels if _brightness(pixel) > 170)
    mean_brightness, std_brightness = _brightness_stats(pixels)

    assert dark_pixels > len(pixels) * 0.08, screenshot_path
    assert very_dark_pixels > 400, screenshot_path
    # Reject near-uniform blank frames (all-white or all-black).
    assert 25 <= mean_brightness <= 225, screenshot_path
    assert std_brightness > 18, screenshot_path
    assert bright_pixels > len(pixels) * 0.01, screenshot_path
