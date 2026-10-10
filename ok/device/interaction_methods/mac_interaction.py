"""
mac_interaction.py - macOS input simulation using CoreGraphics CGEvent API.

Replaces PostMessageInteraction, PynputInteraction, etc. for macOS.
Requires Accessibility permissions to send synthetic keyboard/mouse events.
"""
import time

from ok.device.interaction_methods.base import BaseInteraction
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

# Try to import Quartz; will be available on macOS with pyobjc
try:
    import Quartz
    from AppKit import NSApplication
    _HAS_QUARTZ = True
except ImportError:
    Quartz = None
    NSApplication = None
    _HAS_QUARTZ = False


# macOS CGKeyCode mapping (US keyboard layout, HIToolbox/Events.h)
MAC_KEY_MAP = {
    # Letters (kVK_ANSI_*)
    'a': 0, 'b': 11, 'c': 8, 'd': 2, 'e': 14,
    'f': 3, 'g': 5, 'h': 4, 'i': 34, 'j': 38,
    'k': 40, 'l': 37, 'm': 46, 'n': 45, 'o': 31,
    'p': 35, 'q': 12, 'r': 15, 's': 1, 't': 17,
    'u': 32, 'v': 9, 'w': 13, 'x': 7, 'y': 16,
    'z': 6,

    # Numbers (top number row)
    '1': 18, '2': 19, '3': 20, '4': 21, '5': 23,
    '6': 22, '7': 26, '8': 28, '9': 25, '0': 29,

    # Function keys
    'f1': 122, 'f2': 120, 'f3': 99, 'f4': 118, 'f5': 96,
    'f6': 97, 'f7': 98, 'f8': 100, 'f9': 101, 'f10': 109,
    'f11': 103, 'f12': 111, 'f13': 105, 'f14': 107, 'f15': 113,
    'f16': 106, 'f17': 64, 'f18': 79, 'f19': 80, 'f20': 90,

    # Punctuation & Symbols
    '-': 27, 'minus': 27,
    '=': 24, 'equal': 24,
    '[': 33, ']': 30,
    '\\': 42, 'backslash': 42,
    ';': 41, 'semicolon': 41,
    "'": 39, 'quote': 39,
    ',': 43, 'comma': 43,
    '.': 47, 'period': 47,
    '/': 44, 'slash': 44,
    '`': 50, 'grave': 50,

    # Navigation & Control
    'escape': 53, 'esc': 53,
    'tab': 48,
    'return': 36, 'enter': 36,
    'space': 49,
    'backspace': 51,
    'delete': 117,
    'up': 126, 'down': 125, 'left': 123, 'right': 124,
    'pageup': 116, 'pagedown': 121, 'page_up': 116, 'page_down': 121,
    'home': 115, 'end': 119, 'insert': 114,

    # Modifiers
    'shift': 56, 'lshift': 56, 'shift_l': 56,
    'rshift': 60, 'shift_r': 60,
    'ctrl': 59, 'lctrl': 59, 'ctrl_l': 59, 'control': 59,
    'rctrl': 62, 'ctrl_r': 62,
    'alt': 58, 'lalt': 58, 'alt_l': 58, 'option': 58,
    'ralt': 61, 'alt_r': 61, 'option_r': 61,
    'cmd': 55, 'cmd_l': 55, 'command': 55, 'super': 55, 'windows': 55, 'meta': 55,
    'rcmd': 54, 'cmd_r': 54,
    'caps_lock': 57, 'capslock': 57,
    'fn': 63,
}


# Modifier flag masks for CGEventSetFlags
MODIFIER_FLAGS = {
    'fn': getattr(Quartz, 'kCGEventFlagMaskSecondaryFn', 0x00800000) if Quartz else 0x00800000,
    'cmd': getattr(Quartz, 'kCGEventFlagMaskCommand', 0x00100000) if Quartz else 0x00100000,
    'command': getattr(Quartz, 'kCGEventFlagMaskCommand', 0x00100000) if Quartz else 0x00100000,
    'super': getattr(Quartz, 'kCGEventFlagMaskCommand', 0x00100000) if Quartz else 0x00100000,
    'shift': getattr(Quartz, 'kCGEventFlagMaskShift', 0x00020000) if Quartz else 0x00020000,
    'lshift': getattr(Quartz, 'kCGEventFlagMaskShift', 0x00020000) if Quartz else 0x00020000,
    'rshift': getattr(Quartz, 'kCGEventFlagMaskShift', 0x00020000) if Quartz else 0x00020000,
    'alt': getattr(Quartz, 'kCGEventFlagMaskAlternate', 0x00080000) if Quartz else 0x00080000,
    'lalt': getattr(Quartz, 'kCGEventFlagMaskAlternate', 0x00080000) if Quartz else 0x00080000,
    'ralt': getattr(Quartz, 'kCGEventFlagMaskAlternate', 0x00080000) if Quartz else 0x00080000,
    'option': getattr(Quartz, 'kCGEventFlagMaskAlternate', 0x00080000) if Quartz else 0x00080000,
    'ctrl': getattr(Quartz, 'kCGEventFlagMaskControl', 0x00040000) if Quartz else 0x00040000,
    'lctrl': getattr(Quartz, 'kCGEventFlagMaskControl', 0x00040000) if Quartz else 0x00040000,
    'rctrl': getattr(Quartz, 'kCGEventFlagMaskControl', 0x00040000) if Quartz else 0x00040000,
    'control': getattr(Quartz, 'kCGEventFlagMaskControl', 0x00040000) if Quartz else 0x00040000,
}


def _has_accessibility_permissions(prompt=False):
    """Check if the current process has Accessibility (AX) permissions."""
    try:
        import ApplicationServices
        if prompt and hasattr(ApplicationServices, 'AXIsProcessTrustedWithOptions') and hasattr(ApplicationServices, 'kAXTrustedCheckOptionPrompt'):
            return bool(ApplicationServices.AXIsProcessTrustedWithOptions(
                {ApplicationServices.kAXTrustedCheckOptionPrompt: True}
            ))
        return bool(ApplicationServices.AXIsProcessTrusted())
    except Exception as e:
        logger.warning(f"mac_interaction: could not check AX permissions: {e}")
    return True


def _get_accessibility_prompt():
    """Return instructions for granting Accessibility permissions."""
    return (
        "需要辅助功能权限来模拟键盘/鼠标。\n"
        "请前往：系统偏好设置 > 安全性与隐私 > 隐私 > 辅助功能，\n"
        "然后将此程序添加到允许列表中。\n\n"
        "For English: Go to System Settings > Privacy & Security > Accessibility "
        "and add this application."
    )


class MacInteraction(BaseInteraction):
    """
    macOS input simulation via CGEvent API.
    Uses CGEventPost(kCGHIDEventTap) to send keyboard and mouse events.

    CGEventPost sends events to the system-wide event queue, so the target
    window must be frontmost to receive them.  _auto_activate() brings the
    game window to the front (throttled to at most once per second) before
    each interaction to ensure events reach the correct window.
    """

    # Minimum interval (seconds) between automatic window activations.
    # Prevents stealing focus on every single event while still keeping
    # the game window in front during automation.
    _ACTIVATE_INTERVAL = 1.0

    def __init__(self, capture):
        super().__init__(capture)
        self._has_permissions = None
        self._has_prompted = False
        self._last_perm_warning_time = 0
        self._key_up_event_cache = {}
        self._key_down_event_cache = {}
        self._last_activate_time = 0

    def _ensure_permissions(self):
        """Check and refresh accessibility permissions, throttling warning logs."""
        trusted = _has_accessibility_permissions()
        if trusted:
            self._has_permissions = True
            return True

        self._has_permissions = False
        now = time.time()
        if not self._has_prompted:
            self._has_prompted = True
            _has_accessibility_permissions(prompt=True)

        if now - self._last_perm_warning_time > 30:
            self._last_perm_warning_time = now
            logger.warning(_get_accessibility_prompt())
        return False

    def _auto_activate(self):
        """
        Bring the game window to front if enough time has elapsed.

        CGEventPost sends events to the system event queue; they are received
        by whichever window is frontmost at the target coordinates.  Without
        activation, clicks and keys may land on the OK-WW GUI or another app
        instead of the game.

        Throttled by _ACTIVATE_INTERVAL to avoid stealing focus on every
        single event during rapid automation loops.
        """
        now = time.time()
        if now - self._last_activate_time < self._ACTIVATE_INTERVAL:
            return
        self._last_activate_time = now
        try:
            if self.capture and hasattr(self.capture, 'mac_window'):
                mac_window = self.capture.mac_window
                # Activate only when the game window exists but is NOT the
                # frontmost app — keyboard/mouse events would otherwise land
                # on whichever app currently has focus.
                if mac_window and mac_window.exists and not mac_window.is_frontmost():
                    mac_window.bring_to_front()
        except Exception as e:
            logger.debug(f"MacInteraction _auto_activate error", e)

    def _get_key_code(self, key):
        """Convert key name to macOS CGKeyCode. Returns None for unknown keys."""
        key = str(key).lower().strip()
        return MAC_KEY_MAP.get(key, None)

    def _parse_keys(self, key):
        """Parse key string which may contain '+' combinations (e.g. 'fn+f2', 'ctrl+c')."""
        if not key:
            return []
        key_str = str(key).strip().lower()
        if '+' in key_str:
            return [k.strip() for k in key_str.split('+') if k.strip()]
        return [key_str]

    def _send_single_key(self, key, is_down=True, extra_flags=0):
        key_code = self._get_key_code(key)
        if key_code is None or key_code < 0:
            return
        try:
            self._ensure_permissions()
            event = Quartz.CGEventCreateKeyboardEvent(None, key_code, is_down)
            if not event:
                return
            # macOS F1-F12 keys always carry SecondaryFn flag; combine with extra flags
            flags = Quartz.CGEventGetFlags(event)
            is_fn_key = (122 >= key_code >= 96) or key_code in (109, 103, 111, 105, 107, 113, 106)
            combined_flags = flags | extra_flags
            if is_fn_key and ('fn' in MODIFIER_FLAGS):
                combined_flags |= MODIFIER_FLAGS['fn']
            if combined_flags != flags:
                Quartz.CGEventSetFlags(event, combined_flags)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        except Exception as e:
            logger.error(f"MacInteraction _send_single_key: {key} -> {key_code}", e)

    def send_key(self, key, down_time=0.05):
        super().send_key(key, down_time)
        self._auto_activate()
        keys = self._parse_keys(key)
        if not keys:
            return
        if len(keys) == 1:
            self._send_single_key(keys[0], is_down=True)
            time.sleep(down_time)
            self._send_single_key(keys[0], is_down=False)
        else:
            # Combo keys (e.g. 'fn+f2'): press modifiers in order, then main key with flags
            modifiers = keys[:-1]
            main_key = keys[-1]
            flag_mask = 0
            for m in modifiers:
                if m in MODIFIER_FLAGS:
                    flag_mask |= MODIFIER_FLAGS[m]
                self._send_single_key(m, is_down=True)
            self._send_single_key(main_key, is_down=True, extra_flags=flag_mask)
            time.sleep(down_time)
            self._send_single_key(main_key, is_down=False, extra_flags=flag_mask)
            for m in reversed(modifiers):
                self._send_single_key(m, is_down=False)

    def send_key_down(self, key):
        self._auto_activate()
        keys = self._parse_keys(key)
        for k in keys:
            self._send_single_key(k, is_down=True)

    def send_key_up(self, key):
        keys = self._parse_keys(key)
        for k in reversed(keys):
            self._send_single_key(k, is_down=False)

    def move(self, x, y, down_btn=0):
        """Move cursor to position (x, y) in game coordinates."""
        abs_x, abs_y = self.capture.get_abs_cords(x, y)
        try:
            self._ensure_permissions()
            event = Quartz.CGEventCreateMouseEvent(
                None, Quartz.kCGEventMouseMoved, (abs_x, abs_y), 0
            )
            Quartz.CGEventPost(Quartz.kCGSessionEventTap, event)
        except Exception as e:
            logger.error(f"MacInteraction move: {x},{y} -> {abs_x},{abs_y}", e)

    def click(self, x=-1, y=-1, move_back=False, name=None, move=True, down_time=0.05, key="left"):
        super().click(x, y, name=name)
        self._auto_activate()
        if move or x == -1 or y == -1:
            if x == -1 or y == -1:
                x, y = 0, 0  # Don't move for -1 coords
            else:
                self.move(x, y)
                time.sleep(down_time)

        # Use absolute coordinates (already converted by move or provided)
        if x == -1 or y == -1:
            x, y = 0, 0

        abs_x, abs_y = self.capture.get_abs_cords(x, y)

        try:
            self._ensure_permissions()
            btn_down = Quartz.kCGEventLeftMouseDown
            btn_up = Quartz.kCGEventLeftMouseUp
            mouse_btn = Quartz.kCGMouseButtonLeft
            btn_number = 0
            if key == "right":
                btn_down = Quartz.kCGEventRightMouseDown
                btn_up = Quartz.kCGEventRightMouseUp
                mouse_btn = Quartz.kCGMouseButtonRight
                btn_number = 1
            elif key == "middle":
                btn_down = Quartz.kCGEventOtherMouseDown
                btn_up = Quartz.kCGEventOtherMouseUp
                mouse_btn = Quartz.kCGMouseButtonCenter
                btn_number = 2

            event_down = Quartz.CGEventCreateMouseEvent(None, btn_down, (abs_x, abs_y), mouse_btn)
            if key == "middle" and hasattr(Quartz, 'kCGMouseEventButtonNumber'):
                Quartz.CGEventSetIntegerValueField(event_down, Quartz.kCGMouseEventButtonNumber, btn_number)
            Quartz.CGEventPost(Quartz.kCGSessionEventTap, event_down)
            time.sleep(down_time)
            event_up = Quartz.CGEventCreateMouseEvent(None, btn_up, (abs_x, abs_y), mouse_btn)
            if key == "middle" and hasattr(Quartz, 'kCGMouseEventButtonNumber'):
                Quartz.CGEventSetIntegerValueField(event_up, Quartz.kCGMouseEventButtonNumber, btn_number)
            Quartz.CGEventPost(Quartz.kCGSessionEventTap, event_up)
        except Exception as e:
            logger.error(f"MacInteraction click: {x},{y} -> {abs_x},{abs_y}", e)

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        self._auto_activate()
        if x == -1 or y == -1:
            x, y = 0, 0
        abs_x, abs_y = self.capture.get_abs_cords(x, y)

        try:
            self._ensure_permissions()
            btn = Quartz.kCGEventLeftMouseDown
            mouse_btn = Quartz.kCGMouseButtonLeft
            btn_number = 0
            if key == "right":
                btn = Quartz.kCGEventRightMouseDown
                mouse_btn = Quartz.kCGMouseButtonRight
                btn_number = 1
            elif key == "middle":
                btn = Quartz.kCGEventOtherMouseDown
                mouse_btn = Quartz.kCGMouseButtonCenter
                btn_number = 2

            event = Quartz.CGEventCreateMouseEvent(None, btn, (abs_x, abs_y), mouse_btn)
            if key == "middle" and hasattr(Quartz, 'kCGMouseEventButtonNumber'):
                Quartz.CGEventSetIntegerValueField(event, Quartz.kCGMouseEventButtonNumber, btn_number)
            Quartz.CGEventPost(Quartz.kCGSessionEventTap, event)
        except Exception as e:
            logger.error(f"MacInteraction mouse_down: {x},{y}", e)

    def mouse_up(self, key="left"):
        try:
            self._ensure_permissions()
            # Get current cursor position
            event = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, (0, 0), 0)
            pos = Quartz.CGEventGetLocation(event)
            abs_x, abs_y = pos.x, pos.y

            btn = Quartz.kCGEventLeftMouseUp
            mouse_btn = Quartz.kCGMouseButtonLeft
            btn_number = 0
            if key == "right":
                btn = Quartz.kCGEventRightMouseUp
                mouse_btn = Quartz.kCGMouseButtonRight
                btn_number = 1
            elif key == "middle":
                btn = Quartz.kCGEventOtherMouseUp
                mouse_btn = Quartz.kCGMouseButtonCenter
                btn_number = 2

            event_up = Quartz.CGEventCreateMouseEvent(None, btn, (abs_x, abs_y), mouse_btn)
            if key == "middle" and hasattr(Quartz, 'kCGMouseEventButtonNumber'):
                Quartz.CGEventSetIntegerValueField(event_up, Quartz.kCGMouseEventButtonNumber, btn_number)
            Quartz.CGEventPost(Quartz.kCGSessionEventTap, event_up)
        except Exception as e:
            logger.error(f"MacInteraction mouse_up", e)

    def swipe(self, x1, y1, x2, y2, duration=3, settle_time=0):
        """Smooth mouse drag from (x1, y1) to (x2, y2)."""
        self._auto_activate()
        abs_x1, abs_y1 = self.capture.get_abs_cords(x1, y1)
        abs_x2, abs_y2 = self.capture.get_abs_cords(x2, y2)

        try:
            self._ensure_permissions()
            # Move to start
            self.move(x1, y1)
            time.sleep(0.1)

            # Press left button down
            event_down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown,
                                                        (abs_x1, abs_y1), 0)
            Quartz.CGEventPost(Quartz.kCGSessionEventTap, event_down)

            # Interpolate
            steps = max(int(duration / 0.01), 1)
            dx = (abs_x2 - abs_x1) / steps
            dy = (abs_y2 - abs_y1) / steps

            for i in range(steps):
                pos = (abs_x1 + int(i * dx), abs_y1 + int(i * dy))
                move_event = Quartz.CGEventCreateMouseEvent(
                    None, Quartz.kCGEventMouseMoved, pos, 0
                )
                Quartz.CGEventPost(Quartz.kCGSessionEventTap, move_event)
                time.sleep(0.01)

            # Release
            release_event = Quartz.CGEventCreateMouseEvent(
                None, Quartz.kCGEventLeftMouseUp, (abs_x2, abs_y2), 0
            )
            Quartz.CGEventPost(Quartz.kCGSessionEventTap, release_event)
        except Exception as e:
            logger.error(f"MacInteraction swipe: {x1},{y1} -> {x2},{y2}", e)

    def scroll(self, x, y, scroll_amount):
        """Scroll mouse wheel at position (x, y). scroll_amount > 0 = scroll up."""
        self._auto_activate()
        abs_x, abs_y = self.capture.get_abs_cords(x, y)
        try:
            self._ensure_permissions()
            # Move cursor to position first
            move_event = Quartz.CGEventCreateMouseEvent(
                None, Quartz.kCGEventMouseMoved, (abs_x, abs_y), 0
            )
            Quartz.CGEventPost(Quartz.kCGSessionEventTap, move_event)

            # Scroll wheel event
            wheel_event = Quartz.CGEventCreateMouseEvent(
                None, Quartz.kCGEventScrollWheel, (abs_x, abs_y), 0
            )
            # kCGScrollWheelEventDeltaAxis1 = 0
            wheel_event.setIntegerValueForField_(20, scroll_amount * 10)
            Quartz.CGEventPost(Quartz.kCGSessionEventTap, wheel_event)
        except Exception as e:
            logger.error(f"MacInteraction scroll: {x},{y} amount={scroll_amount}", e)

    def input_text(self, text):
        """Type text by sending individual character events."""
        self._auto_activate()
        for char in text:
            key_code = self._get_key_code(char)
            try:
                self._ensure_permissions()
                event_down = Quartz.CGEventCreateKeyboardEvent(None, key_code, True)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, event_down)
                time.sleep(0.01)
                event_up = Quartz.CGEventCreateKeyboardEvent(None, key_code, False)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, event_up)
            except Exception as e:
                logger.error(f"MacInteraction input_text: {char}", e)
                time.sleep(0.01)

    def activate(self):
        """Activate the game window."""
        if self.capture and hasattr(self.capture, 'mac_window'):
            mac_window = self.capture.mac_window
            if mac_window:
                mac_window.bring_to_front()

    def should_capture(self):
        return True
