import sys

from ok.device.capture_methods.adb import ADBCaptureMethod
from ok.device.capture_methods.base import BaseCaptureMethod, BaseWindowsCaptureMethod
from ok.device.capture_methods.image import ImageCaptureMethod
from ok.device.capture_methods.nemu_ipc import NemuIpcCaptureMethod
from ok.device.capture_methods.types import ColorChannel, ImageShape, decimal, is_digit, is_valid_hwnd

class _UnavailableCaptureMethod(BaseCaptureMethod):
    """Placeholder for capture methods not available on the current platform."""
    pass


class _UnavailableWindow:
    """Placeholder for window wrappers not available on the current platform."""
    pass


if sys.platform == 'win32':
    from ok.device.capture_methods.bitblt import BitBltCaptureMethod, ForegroundBitBltCaptureMethod
    from ok.device.capture_methods.bitblt_utils import (
        BGRA_CHANNEL_COUNT,
        PBYTE,
        PW_CLIENT_ONLY,
        PW_RENDERFULLCONTENT,
        BitBltCtxDummy,
        capture_by_bitblt,
        capture_desktop_by_bitblt,
        clean_up_bitblt,
        clean_up_desktop_bitblt,
        composite_hwnds,
        get_crop_point,
        parse_reg_flag,
        try_delete_dc,
    )
    from ok.device.capture_methods.browser import BrowserCaptureMethod, BrowserWGC, BrowserWindowAdapter
    from ok.device.capture_methods.desktop_duplication import DesktopDuplicationCaptureMethod
    from ok.device.capture_methods.hwnd_window import HwndWindow, check_pos, get_monitors_bounds, get_mute_state, is_window_in_screen_bounds, set_mute_state
    from ok.device.capture_methods.update import get_capture, get_win_graphics_capture, update_capture_method
    from ok.device.capture_methods.windows_graphics import WindowsGraphicsCaptureMethod
    class MacCaptureMethod(_UnavailableCaptureMethod):
        pass

    class MacCaptureMethodFallback(_UnavailableCaptureMethod):
        pass

    class MacWindow(_UnavailableWindow):
        pass
else:
    class BitBltCaptureMethod(_UnavailableCaptureMethod):
        pass

    class ForegroundBitBltCaptureMethod(_UnavailableCaptureMethod):
        pass

    class BrowserCaptureMethod(_UnavailableCaptureMethod):
        pass

    class BrowserWGC(_UnavailableCaptureMethod):
        pass

    class BrowserWindowAdapter(_UnavailableWindow):
        pass

    class DesktopDuplicationCaptureMethod(_UnavailableCaptureMethod):
        pass

    class HwndWindow(_UnavailableWindow):
        pass

    class WindowsGraphicsCaptureMethod(_UnavailableCaptureMethod):
        pass

    get_capture = None
    get_win_graphics_capture = None
    update_capture_method = None
    BGRA_CHANNEL_COUNT = 0
    PBYTE = None
    PW_CLIENT_ONLY = 0
    PW_RENDERFULLCONTENT = 0
    BitBltCtxDummy = None
    capture_by_bitblt = None
    capture_desktop_by_bitblt = None
    clean_up_bitblt = None
    clean_up_desktop_bitblt = None
    composite_hwnds = None
    get_crop_point = None
    parse_reg_flag = None
    try_delete_dc = None
    check_pos = None
    get_monitors_bounds = None
    get_mute_state = None
    is_window_in_screen_bounds = None
    set_mute_state = None
    if sys.platform == 'darwin':
        from ok.device.capture_methods.mac_capture import MacCaptureMethod, MacCaptureMethodFallback
        from ok.device.capture_methods.mac_window import MacWindow
        from ok.device.capture_methods.update import get_mac_capture, update_mac_capture_method
    else:
        class MacCaptureMethod(_UnavailableCaptureMethod):
            pass

        class MacCaptureMethodFallback(_UnavailableCaptureMethod):
            pass

        class MacWindow(_UnavailableWindow):
            pass
