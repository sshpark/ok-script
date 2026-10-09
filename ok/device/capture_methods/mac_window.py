"""
mac_window.py - macOS equivalent of HwndWindow.

Finds and tracks the Wuthering Waves game window using macOS Quartz/Accessibility APIs.
Uses CGWindowListCopyWindowInfo for window discovery and background polling.
"""
import os
import threading
import time

logger = None  # set during init

try:
    import Quartz
    import AppKit
    from AppKit import NSWorkspace, NSApplication, NSRunningApplication
    from Foundation import NSString
except ImportError:
    Quartz = None
    AppKit = None
    NSWorkspace = None
    NSApplication = None
    NSRunningApplication = None


class MacWindow:
    """
    macOS equivalent of HwndWindow.
    Finds the game window by process name, tracks its bounds.
    """

    KNOWN_GAME_KEYWORDS = ('wuthering', 'kuro', '鸣潮', '鳴潮', 'client-mac-shipping', 'mingchao')
    KNOWN_BUNDLE_KEYWORDS = ('wutheringwaves', 'mingchao', 'kurogame')
    HELPER_KEYWORDS = ('助手', 'ok-ww', 'ok-wuthering-waves', 'ok-script', 'assistant')

    def __init__(self, exit_event, title=None, exe_names=None, frame_width=0, frame_height=0,
                 player_id=-1, global_config=None, device_manager=None):
        global logger
        from ok.util.logger import Logger
        logger = Logger.get_logger(__name__)

        self.app_exit_event = exit_event
        self.stop_event = threading.Event()
        self.title = title
        self.exe_names = None
        self.player_id = player_id
        self.device_manager = device_manager
        self.global_config = global_config

        # Window state
        self.exists = False
        self.visible = False
        self.hwnd = 0  # CGWindowID for API compatibility
        self.game_pid = 0
        self.x = 0
        self.y = 0
        self.width = 0
        self.height = 0
        self.window_width = 0
        self.window_height = 0
        self.real_x_offset = 0
        self.real_y_offset = 0
        self.real_width = 0
        self.real_height = 0
        self.scaling = 1.0
        self.frame_width = 0
        self.frame_height = 0
        self.frame_aspect_ratio = 0
        self.hwnds = []  # kept for API compatibility (list of window infos)
        self.top_hwnd = 0
        self.top_offset_x = 0
        self.top_offset_y = 0
        self.exe_full_path = ""

        self.update_window(title, exe_names, frame_width, frame_height)
        self.thread = threading.Thread(target=self._update_loop, name="MacWindowUpdate")
        self.thread.daemon = True
        self.thread.start()

    def update_window(self, title, exe_name, frame_width, frame_height, player_id=-1,
                      hwnd_class=None, top_hwnd_class=None):
        self.player_id = player_id
        self.title = title
        if isinstance(exe_name, str):
            self.exe_names = [exe_name]
        else:
            self.exe_names = exe_name
        self.update_frame_size(frame_width, frame_height)
        self.hwnd_class = hwnd_class
        self.top_hwnd_class = top_hwnd_class

    def update_frame_size(self, width, height):
        if logger:
            logger.debug(f"update_frame_size: {self.frame_width}x{self.frame_height} to {width}x{height}")
        if width != self.frame_width or height != self.frame_height:
            self.frame_width = width
            self.frame_height = height
            if width > 0 and height > 0:
                self.frame_aspect_ratio = width / height
        self.hwnd = 0
        self.do_update_window_size()

    def _update_loop(self):
        while not self.app_exit_event.is_set() and not self.stop_event.is_set():
            try:
                self.do_update_window_size()
            except Exception as e:
                if logger:
                    logger.error(f"MacWindow update error", e)
            time.sleep(0.2)

    def do_update_window_size(self):
        try:
            changed = False
            old_exists = self.exists
            old_visible = self.visible
            old_x, old_y, old_w, old_h = self.x, self.y, self.width, self.height

            window_id, bounds, owner_name = self._find_game_window()

            if window_id and window_id != self.hwnd:
                self.hwnd = window_id
                changed = True

            if window_id:
                self.exists = True
                self.real_x_offset = 0
                self.real_y_offset = 0
                self.real_width = 0
                self.real_height = 0
                self.top_hwnd = window_id
                self.top_offset_x = 0
                self.top_offset_y = 0
                self.exe_full_path = ""
                self.hwnds = [(window_id, owner_name or "", 0, 0, 0, 0, 0, 0)]

                x = int(bounds.get('X', 0))
                y = int(bounds.get('Y', 0))
                w = int(bounds.get('Width', 0))
                h = int(bounds.get('Height', 0))

                # macOS: is_foreground() checks if window is visible on screen
                visible = self.is_foreground()
                if visible != self.visible:
                    self.visible = visible
                    changed = True

                if (x != self.x or y != self.y or w != self.width or h != self.height):
                    self.x = x
                    self.y = y
                    self.width = w
                    self.height = h
                    self.window_width = w
                    self.window_height = h
                    changed = True
            else:
                if self.exists:
                    changed = True
                self.exists = False
                self.visible = False
                self.hwnd = 0
                self.hwnds = []

            if changed or old_exists != self.exists or old_visible != self.visible:
                if logger:
                    logger.info(
                        f"MacWindow changed: exists={self.exists}, visible={self.visible}, "
                        f"x={self.x} y={self.y} w={self.width} h={self.height}"
                    )
                if self.device_manager:
                    device = self.device_manager.get_preferred_device()
                    if device:
                        device['connected'] = self.exists
                        if self.exists:
                            device['width'] = self.width
                            device['height'] = self.height
                            device['resolution'] = f"{self.width}x{self.height}"
        except Exception as e:
            if logger:
                logger.error(f"MacWindow do_update_window_size exception", e)

    def _find_game_window(self):
        """
        Find the Wuthering Waves window using CGWindowListCopyWindowInfo.
        Returns (window_id, bounds_dict, owner_name) or (None, None, None).
        """
        if not Quartz:
            return None, None, None

        try:
            window_list = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly,
                Quartz.kCGNullWindowID
            )
        except Exception as e:
            if logger:
                logger.error(f"MacWindow find window error", e)
            return None, None, None

        titles = [self.title] if isinstance(self.title, str) else (self.title or [])
        exe_patterns = [self.exe_names] if isinstance(self.exe_names, str) else (self.exe_names or [])

        candidates = []
        my_pid = os.getpid()
        ppid = os.getppid()
        pids_to_ignore = {my_pid, ppid}

        for w in window_list:
            pid = w.get('kCGWindowOwnerPID', 0)
            if pid in pids_to_ignore:
                continue

            owner = (w.get('kCGWindowOwnerName') or '').strip()
            name = (w.get('kCGWindowName') or '').strip()
            owner_lower = owner.lower()
            name_lower = name.lower()

            if any(hk in owner_lower or hk in name_lower for hk in self.HELPER_KEYWORDS):
                continue

            matched = False
            # 1. Match by explicit title(s)
            for t in titles:
                t_lower = t.lower()
                if t_lower and (t_lower in owner_lower or t_lower in name_lower):
                    matched = True
                    break

            # 2. Match by explicit process / pattern(s)
            if not matched:
                for p in exe_patterns:
                    p_lower = p.lower()
                    p_base = p_lower[:-4] if p_lower.endswith('.app') else p_lower
                    if p_lower in owner_lower or p_lower in name_lower or p_base in owner_lower or p_base in name_lower:
                        matched = True
                        break

            # 3. Fallback: match by known game keywords
            if not matched:
                for kw in self.KNOWN_GAME_KEYWORDS:
                    if kw in owner_lower or kw in name_lower:
                        matched = True
                        break

            if matched:
                candidates.append(w)

        if not candidates:
            return None, None, None

        # Filter out auxiliary/status bar/tiny windows
        valid_candidates = [
            w for w in candidates
            if (w.get('kCGWindowBounds', {}).get('Width', 0) or 0) >= 200
            and (w.get('kCGWindowBounds', {}).get('Height', 0) or 0) >= 200
        ]
        if not valid_candidates:
            valid_candidates = candidates

        # Pick the largest window (the game window)
        best = max(valid_candidates, key=lambda w: (
            w.get('kCGWindowBounds', {}).get('Width', 0) or 0
        ) * (w.get('kCGWindowBounds', {}).get('Height', 0) or 0))

        bounds = best.get('kCGWindowBounds', {})
        owner = best.get('kCGWindowOwnerName', '') or best.get('kCGWindowName', '')
        self.game_pid = int(best.get('kCGWindowOwnerPID', 0))
        return best['kCGWindowNumber'], bounds, owner

    def get_abs_cords(self, x, y):
        """Convert game-relative coordinates to screen coordinates."""
        scale = self.scaling if self.scaling > 0 else 1.0
        return self.x + int(x / scale), self.y + int(y / scale)

    def get_top_window_cords(self, x, y):
        """Equivalent of HwndWindow.get_top_window_cords."""
        return x - self.top_offset_x, y - self.top_offset_y

    def bring_to_front(self):
        """Activate the game window."""
        if not self.exists or not NSWorkspace:
            return False
        try:
            flag = getattr(AppKit, 'NSApplicationActivateIgnoringOtherApps', 1 << 1)
            # 1. Prefer activating directly by PID if known
            if self.game_pid and NSRunningApplication:
                app = NSRunningApplication.runningApplicationWithProcessIdentifier_(self.game_pid)
                if app:
                    app.activateWithOptions_(flag)
                    return True

            # 2. Fallback: match running application by keyword, ignoring ourselves
            my_pid = os.getpid()
            ws = NSWorkspace.sharedWorkspace()
            for app in ws.runningApplications():
                if app.processIdentifier() == my_pid:
                    continue
                app_name = (app.localizedName() or '').lower()
                bundle_id = (app.bundleIdentifier() or '').lower()
                if any(hk in app_name or hk in bundle_id for hk in self.HELPER_KEYWORDS):
                    continue
                if (any(k in app_name for k in self.KNOWN_GAME_KEYWORDS) or
                        any(b in bundle_id for b in self.KNOWN_BUNDLE_KEYWORDS)):
                    app.activateWithOptions_(flag)
                    return True
        except Exception as e:
            if logger:
                logger.error(f"MacWindow bring_to_front error", e)
        return False

    def is_foreground(self):
        """
        Check if game window is visible on screen (not necessarily frontmost).
        """
        if not Quartz:
            if not NSWorkspace:
                return False
            try:
                front_app = NSWorkspace.sharedWorkspace().frontmostApplication()
                if front_app:
                    if front_app.processIdentifier() == os.getpid():
                        return False
                    name = (front_app.localizedName() or '').lower()
                    bundle_id = (front_app.bundleIdentifier() or '').lower()
                    if any(hk in name or hk in bundle_id for hk in self.HELPER_KEYWORDS):
                        return False
                    return (any(k in name for k in self.KNOWN_GAME_KEYWORDS) or
                            any(b in bundle_id for b in self.KNOWN_BUNDLE_KEYWORDS))
            except Exception as e:
                if logger:
                    logger.error(f"MacWindow is_foreground fallback error", e)
            return False

        try:
            # Primary check: is the game window in the on-screen window list?
            if self.hwnd:
                window_list = Quartz.CGWindowListCopyWindowInfo(
                    Quartz.kCGWindowListOptionOnScreenOnly,
                    Quartz.kCGNullWindowID
                )
                for w in (window_list or []):
                    if w.get('kCGWindowNumber') == self.hwnd:
                        return True
        except Exception as e:
            if logger:
                logger.error(f"MacWindow is_foreground error", e)

        # Secondary fallback: check if game is the frontmost application
        try:
            if NSWorkspace:
                front_app = NSWorkspace.sharedWorkspace().frontmostApplication()
                if front_app:
                    if front_app.processIdentifier() == os.getpid():
                        return False
                    name = (front_app.localizedName() or '').lower()
                    bundle_id = (front_app.bundleIdentifier() or '').lower()
                    if any(hk in name or hk in bundle_id for hk in self.HELPER_KEYWORDS):
                        return False
                    return (any(k in name for k in self.KNOWN_GAME_KEYWORDS) or
                            any(b in bundle_id for b in self.KNOWN_BUNDLE_KEYWORDS))
        except Exception as e:
            if logger:
                logger.error(f"MacWindow is_foreground frontmost fallback error", e)

        return False

    def is_frontmost(self):
        """
        Check if the game is the frontmost (active) application.
        """
        if not NSWorkspace:
            return False
        try:
            front_app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if not front_app:
                return False
            pid = front_app.processIdentifier()
            if pid == os.getpid():
                return False
            if self.game_pid and pid == self.game_pid:
                return True
            name = (front_app.localizedName() or '').lower()
            bundle_id = (front_app.bundleIdentifier() or '').lower()
            if any(hk in name or hk in bundle_id for hk in self.HELPER_KEYWORDS):
                return False
            return (any(k in name for k in self.KNOWN_GAME_KEYWORDS) or
                    any(b in bundle_id for b in self.KNOWN_BUNDLE_KEYWORDS))
        except Exception as e:
            if logger:
                logger.error(f"MacWindow is_frontmost error", e)
        return False

    def capture_target_signature(self):
        return (self.hwnd, self.top_hwnd, self.width, self.height,
                self.real_x_offset, self.real_y_offset, self.real_width,
                self.real_height, tuple(h[0] for h in self.hwnds))

    def stop(self):
        self.stop_event.set()

    def try_resize_to(self, resize_to):
        """macOS: Try resizing the game window via Accessibility API."""
        if not self.game_pid or not resize_to:
            return False
        try:
            from ApplicationServices import (
                AXUIElementCreateApplication,
                AXUIElementCopyAttributeValue,
                AXUIElementSetAttributeValue,
                AXValueCreate,
                kAXValueCGSizeType,
                kAXWindowsAttribute,
                kAXSizeAttribute,
            )
            app = AXUIElementCreateApplication(self.game_pid)
            err, windows = AXUIElementCopyAttributeValue(app, kAXWindowsAttribute, None)
            if err != 0 or not windows:
                return False

            main_display = Quartz.CGMainDisplayID()
            screen_w = Quartz.CGDisplayPixelsWide(main_display)
            screen_h = Quartz.CGDisplayPixelsHigh(main_display)

            target_w, target_h = None, None
            for res in resize_to:
                if screen_w >= res[0] and screen_h >= res[1]:
                    target_w, target_h = res[0], res[1]
                    break
            if not target_w:
                target_w, target_h = resize_to[-1]

            scale = self.scaling if self.scaling > 0 else 1.0
            pts_w = target_w / scale
            pts_h = target_h / scale

            for win in windows:
                size_val = AXValueCreate(kAXValueCGSizeType, Quartz.CGSizeMake(pts_w, pts_h))
                err = AXUIElementSetAttributeValue(win, kAXSizeAttribute, size_val)
                if err == 0:
                    if logger:
                        logger.info(f"MacWindow resized game window to {pts_w}x{pts_h} points ({target_w}x{target_h})")
                    time.sleep(0.5)
                    self.do_update_window_size()
                    return True
        except Exception as e:
            if logger:
                logger.warning(f"MacWindow try_resize_to failed: {e}")
        return False

    def frame_ratio(self, size):
        if self.frame_width > 0 and self.width > 0:
            return int(size / self.frame_width * self.width)
        return size

    def __str__(self):
        return (f"title_{self.title}_{self.exe_names}_"
                f"{self.width}x{self.height}_{self.hwnd}_{self.exists}_{self.visible}")
