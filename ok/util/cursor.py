"""
cursor.py - Platform-agnostic cursor position helpers.

Usage:
    from ok.util.cursor import get_cursor_pos, set_cursor_pos
    pos = get_cursor_pos()  # (x, y)
    set_cursor_pos(500, 500)
"""
import platform


def get_cursor_pos():
    """Get the current cursor position in screen coordinates."""
    system = platform.system()
    if system == 'Darwin':
        return _mac_get_cursor_pos()
    else:
        return _win_get_cursor_pos()


def set_cursor_pos(x, y):
    """Set the cursor position to (x, y) in screen coordinates."""
    system = platform.system()
    if system == 'Darwin':
        _mac_set_cursor_pos(x, y)
    else:
        _win_set_cursor_pos((x, y))


def _mac_get_cursor_pos():
    from AppKit import NSEvent, NSScreen
    # NSEvent.mouseLocation returns position with origin at bottom-left
    mouse_loc = NSEvent.mouseLocation()
    # Convert to top-left origin (same as CGWindowList coordinates)
    screen_height = NSScreen.mainScreen().frame().size.height
    x = int(mouse_loc.x)
    y = int(screen_height - mouse_loc.y)
    return (x, y)


def _mac_set_cursor_pos(x, y):
    import Quartz
    # CGEventPost with kCGHIDEventTap to actually move the cursor
    event = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventMouseMoved, (float(x), float(y)), 0
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def _win_get_cursor_pos():
    import win32api
    return win32api.GetCursorPos()


def _win_set_cursor_pos(pos):
    import win32api
    win32api.SetCursorPos(pos)
