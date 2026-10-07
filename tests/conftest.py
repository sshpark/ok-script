import sys
from types import ModuleType
from unittest.mock import MagicMock

if sys.platform != 'win32':
    class Win32Con(ModuleType):
        WM_ACTIVATE = 0x0006
        WM_SETFOCUS = 0x0007
        WM_KILLFOCUS = 0x0008
        WM_CLOSE = 0x0010
        WM_CHAR = 0x0102
        WM_KEYDOWN = 0x0100
        WM_KEYUP = 0x0101
        WM_SYSKEYDOWN = 0x0104
        WM_SYSKEYUP = 0x0105
        WM_MOUSEMOVE = 0x0200
        WM_LBUTTONDOWN = 0x0201
        WM_LBUTTONUP = 0x0202
        WM_RBUTTONDOWN = 0x0204
        WM_RBUTTONUP = 0x0205
        VK_BACK = 0x08
        VK_TAB = 0x09
        VK_RETURN = 0x0D
        VK_SHIFT = 0x10
        VK_CONTROL = 0x11
        VK_MENU = 0x12
        VK_ESCAPE = 0x1B
        VK_SPACE = 0x20
        VK_END = 0x23
        VK_HOME = 0x24
        VK_LEFT = 0x25
        VK_UP = 0x26
        VK_RIGHT = 0x27
        VK_DOWN = 0x28
        VK_DELETE = 0x2E
        CF_DIB = 8
        CF_UNICODETEXT = 13
        WA_ACTIVE = 1
        MK_LBUTTON = 0x0001

        def __getattr__(self, name):
            val = abs(hash(name)) % 65536
            setattr(self, name, val)
            return val

    win32con_mod = Win32Con('win32con')
    sys.modules['win32con'] = win32con_mod

    class Win32Api(MagicMock):
        @staticmethod
        def MAKELONG(wLow, wHigh):
            return ((int(wLow) & 0xffff) | ((int(wHigh) & 0xffff) << 16))

    for mod_name in ['win32gui', 'win32process', 'win32ui', 'win32clipboard', 'win32com', 'win32com.client']:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = MagicMock()

    if 'win32api' not in sys.modules:
        sys.modules['win32api'] = Win32Api()

    import ctypes
    if not hasattr(ctypes, 'windll'):
        ctypes.windll = MagicMock()

    if sys.platform == 'darwin':
        try:
            import qframelesswindow.mac as qf_mac
            from PySide6.QtGui import QGuiApplication
            _orig_updateFrameless = qf_mac.MacFramelessWindowBase.updateFrameless

            def _safe_updateFrameless(self):
                if QGuiApplication.platformName() == 'offscreen':
                    setattr(self, '_MacFramelessWindowBase__nsWindow', MagicMock())
                    return
                try:
                    _orig_updateFrameless(self)
                except Exception:
                    setattr(self, '_MacFramelessWindowBase__nsWindow', MagicMock())

            qf_mac.MacFramelessWindowBase.updateFrameless = _safe_updateFrameless
            qf_mac.MacWindowEffect.setAcrylicEffect = lambda *args, **kwargs: None
            qf_mac.MacWindowEffect.removeAcrylicEffect = lambda *args, **kwargs: None
        except Exception:
            pass
