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


# macOS CGKeyCode mapping (US keyboard layout)
# Source: https://developer.apple.com/documentation/coregraphics/cgeventkeyboard
MAC_KEY_MAP = {
    # Function keys
    'f1': 122, 'f2': 120, 'f3': 99, 'f4': 118, 'f5': 96,
    'f6': 97, 'f7': 98, 'f8': 100, 'f9': 101, 'f10': 108,
    'f11': 104, 'f12': 109, 'f13': 103, 'f14': 105,
    'f15': 107, 'f16': 106, 'f17': 60, 'f18': 88, 'f19': 87,
    # Navigation
    'escape': 53, 'esc': 53,
    'tab': 48,
    'return': 36, 'enter': 36,
    'space': 49,
    'backspace': 51,
    'delete': 117,
    # Arrow keys
    'up': 126, 'down': 125, 'left': 123, 'right': 124,
    'pageup': 116, 'pagedown': 121, 'page_up': 116, 'page_down': 121,
    'home': 115, 'end': 119, 'insert': 114,
    # Modifiers
    'shift': 56, 'lshift': 56, 'rshift': 59, 'shift_l': 56, 'shift_r': 59,
    'ctrl': 59, 'lctrl': 59, 'rctrl': 62, 'lcontrol': 59, 'rcontrol': 62, 'ctrl_l': 59, 'ctrl_r': 62,
    'alt': 58, 'lalt': 58, 'ralt': 61, 'alt_l': 58, 'alt_r': 61,
    # Command key (macOS super key)
    'cmd': 55, 'cmd_l': 55, 'cmd_r': 55, 'command': 55, 'windows': 55, 'meta': 55,
    # Caps lock
    'caps_lock': 57, 'capslock': 57,
}


def _has_accessibility_permissions():
    """Check if the current process has Accessibility (AX) permissions."""
    try:
        import ApplicationServices
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
        self._key_up_event_cache = {}
        self._key_down_event_cache = {}
        self._last_activate_time = 0

    def _ensure_permissions(self):
        """Check and cache accessibility permissions."""
        if self._has_permissions is None:
            self._has_permissions = _has_accessibility_permissions()
        if not self._has_permissions:
            logger.warning(_get_accessibility_prompt())
        return self._has_permissions

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
        """Convert key name to macOS CGKeyCode."""
        key = str(key).lower().strip()

        # Direct map lookup
        if key in MAC_KEY_MAP:
            return MAC_KEY_MAP[key]

        # Single character: find key code from the key
        # Try to get the key code for a letter/digit
        if len(key) == 1:
            # Build a key-down event from the character
            # CGEventCreateKeyboardEvent with key=0 and shift=False sends the character
            try:
                from Quartz import CGEventCreateKeyboardEvent, CGEventGetIntegerValueField, kCGKeyboardEventKeycode
                event = CGEventCreateKeyboardEvent(None, 0, True)
                if event:
                    # Create a character event
                    char_event = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
                    char_event.setIntegerValueForField_(
                        Quartz.kCGKeyboardEventKeycode, 0
                    )
                    # Try to get key code from the character using NSEvent
                    from AppKit import NSEvent
                    # Use a simpler approach: find the key code for the character
                    # by checking standard key positions
                    char_lower = key.lower()
                    # Letter keys: a=0, b=1, ... (US layout standard)
                    # Actually, let's use the character directly
                    if char_lower >= 'a' and char_lower <= 'z':
                        # US layout: A=0, B=1, C=2, ...
                        return ord(char_lower) - ord('a')
                    elif char_lower >= '0' and char_lower <= '9':
                        # US layout: 0=29, 1=18, 2=19, 3=20, 4=21, 5=22, 6=23, 7=24, 8=25, 9=26
                        digits = {'0': 29, '1': 18, '2': 19, '3': 20, '4': 21,
                                  '5': 22, '6': 23, '7': 24, '8': 25, '9': 26}
                        return digits.get(char_lower, 0)
            except Exception:
                pass

        # Default: return 0 (no-op for unknown keys)
        return 0

    def send_key(self, key, down_time=0.02):
        super().send_key(key, down_time)
        self._auto_activate()
        self.send_key_down(key)
        time.sleep(down_time)
        self.send_key_up(key)

    def send_key_down(self, key):
        self._auto_activate()
        key_code = self._get_key_code(key)
        if key_code == 0:
            return
        try:
            self._ensure_permissions()
            event = Quartz.CGEventCreateKeyboardEvent(None, key_code, True)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        except Exception as e:
            logger.error(f"MacInteraction send_key_down: {key} -> {key_code}", e)

    def send_key_up(self, key):
        key_code = self._get_key_code(key)
        if key_code == 0:
            return
        try:
            self._ensure_permissions()
            event = Quartz.CGEventCreateKeyboardEvent(None, key_code, False)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        except Exception as e:
            logger.error(f"MacInteraction send_key_up: {key} -> {key_code}", e)

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
            if key == "right":
                btn_down = Quartz.kCGEventRightMouseDown
                btn_up = Quartz.kCGEventRightMouseUp
            elif key == "middle":
                btn_down = Quartz.kCGEventOtherMouseDown
                btn_up = Quartz.kCGEventOtherMouseUp

            event_down = Quartz.CGEventCreateMouseEvent(None, btn_down, (abs_x, abs_y), 0)
            Quartz.CGEventPost(Quartz.kCGSessionEventTap, event_down)
            time.sleep(down_time)
            event_up = Quartz.CGEventCreateMouseEvent(None, btn_up, (abs_x, abs_y), 0)
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
            if key == "right":
                btn = Quartz.kCGEventRightMouseDown
            elif key == "middle":
                btn = Quartz.kCGEventOtherMouseDown

            event = Quartz.CGEventCreateMouseEvent(None, btn, (abs_x, abs_y), 0)
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
            if key == "right":
                btn = Quartz.kCGEventRightMouseUp
            elif key == "middle":
                btn = Quartz.kCGEventOtherMouseUp

            event_up = Quartz.CGEventCreateMouseEvent(None, btn, (abs_x, abs_y), 0)
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
