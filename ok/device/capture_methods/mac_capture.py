"""
mac_capture.py - macOS screen capture using Quartz Core Graphics.

Replaces BitBltCaptureMethod and WindowsGraphicsCaptureMethod for macOS.
Uses CGWindowListCreateImage to capture screen regions and converts to
BGR numpy arrays for OpenCV compatibility.
"""
import time

import cv2
import numpy as np

from ok.device.capture_methods.base import BaseCaptureMethod
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


def _cgimage_to_bgr(image):
    """
    Convert a CGImage to a BGR numpy array.

    Handles row padding (bytesPerRow != width * 4) and BGRA -> BGR conversion.
    """
    import Quartz

    w = int(Quartz.CGImageGetWidth(image))
    h = int(Quartz.CGImageGetHeight(image))
    bpr = int(Quartz.CGImageGetBytesPerRow(image))

    dp = Quartz.CGImageGetDataProvider(image)
    raw = bytes(Quartz.CGDataProviderCopyData(dp))

    # bytesPerRow may include padding beyond width * 4
    row_pixels = bpr // 4  # 4 bytes per pixel (BGRA)
    arr = np.frombuffer(raw, dtype=np.uint8).reshape((h, row_pixels, 4))
    # Crop to actual width (remove padding)
    arr = arr[:, :w, :]
    # Drop alpha channel -> BGR
    bgr = arr[:, :, :3].copy()
    return bgr


class MacCaptureMethod(BaseCaptureMethod):
    """
    macOS screen capture using CGWindowListCreateImage.
    Captures a specific screen region (game window bounds).
    """

    name = "MacCapture"
    description = "macOS CoreGraphics window capture"

    def __init__(self, exit_event=None, mac_window=None):
        super().__init__()
        self.exit_event = exit_event
        self._mac_window = mac_window
        self._last_frame_time = 0
        self._frame_count = 0

    @property
    def mac_window(self):
        return self._mac_window

    @mac_window.setter
    def mac_window(self, mac_window):
        self._mac_window = mac_window

    def connected(self):
        return self._mac_window is not None and self._mac_window.exists and self._mac_window.hwnd > 0

    def clickable(self):
        return self._mac_window is not None and self._mac_window.visible

    def get_abs_cords(self, x, y):
        """Convert game-relative coordinates to screen coordinates."""
        if self._mac_window:
            return self._mac_window.get_abs_cords(x, y)
        return x, y

    def do_get_frame(self):
        """
        Capture screen and crop to game window region.
        Returns BGR numpy array (OpenCV format).
        """
        import Quartz

        if self.exit_event and self.exit_event.is_set():
            return None

        mac_window = self._mac_window
        if not mac_window or not mac_window.exists:
            return None

        if mac_window.width <= 0 or mac_window.height <= 0:
            return None

        try:
            x = mac_window.x
            y = mac_window.y
            w = mac_window.width
            h = mac_window.height

            # Try direct window capture first if window ID is known
            image = None
            if mac_window.hwnd:
                image = Quartz.CGWindowListCreateImage(
                    Quartz.CGRectNull,
                    Quartz.kCGWindowListOptionIncludingWindow,
                    mac_window.hwnd,
                    Quartz.kCGWindowImageBoundsIgnoreFraming
                )

            # Fallback to cropping screen rectangle
            if not image:
                image = Quartz.CGWindowListCreateImage(
                    Quartz.CGRectMake(x, y, w, h),
                    Quartz.kCGWindowListOptionOnScreenOnly,
                    Quartz.kCGNullWindowID,
                    Quartz.kCGWindowImageDefault
                )

            if not image:
                return None

            bgr = _cgimage_to_bgr(image)
            if w > 0:
                mac_window.scaling = bgr.shape[1] / w
            self._size = (bgr.shape[1], bgr.shape[0])
            self._frame_count += 1
            return bgr

        except Exception as e:
            logger.error(f"MacCapture do_get_frame error", e)
            return None


class MacCaptureMethodFallback(BaseCaptureMethod):
    """
    Fallback capture method: captures entire screen.
    Used when the game window bounds are not yet known.
    """

    name = "MacCaptureFallback"
    description = "macOS CoreGraphics full screen capture (fallback)"

    def __init__(self, exit_event=None, mac_window=None):
        super().__init__()
        self.exit_event = exit_event
        self._mac_window = mac_window

    @property
    def mac_window(self):
        return self._mac_window

    @mac_window.setter
    def mac_window(self, mac_window):
        self._mac_window = mac_window

    def connected(self):
        return True

    def clickable(self):
        return False

    def get_abs_cords(self, x, y):
        if self._mac_window:
            return self._mac_window.get_abs_cords(x, y)
        return x, y

    def do_get_frame(self):
        import Quartz

        if self.exit_event and self.exit_event.is_set():
            return None

        try:
            # CGRectNull + kCGWindowListOptionOnScreenOnly = capture all visible windows
            image = Quartz.CGWindowListCreateImage(
                Quartz.CGRectNull,
                Quartz.kCGWindowListOptionOnScreenOnly,
                Quartz.kCGNullWindowID,
                Quartz.kCGWindowImageDefault
            )

            if not image:
                return None

            bgr = _cgimage_to_bgr(image)
            self._size = (bgr.shape[1], bgr.shape[0])
            return bgr

        except Exception as e:
            logger.error(f"MacCaptureFallback do_get_frame error", e)
            return None
