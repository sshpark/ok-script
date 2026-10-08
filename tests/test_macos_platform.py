import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest

from ok.device.capture_methods.mac_capture import MacCaptureMethod, MacCaptureMethodFallback, _cgimage_to_bgr
from ok.device.capture_methods.mac_window import MacWindow
from ok.device.interaction_methods.mac_interaction import (
    MAC_KEY_MAP, MacInteraction, _has_accessibility_permissions,
)
from ok.util.cursor import get_cursor_pos, set_cursor_pos


class TestMacCapture(unittest.TestCase):
    def test_cgimage_to_bgr_conversion(self):
        # Create a mock CGImage with width 10, height 10, bytesPerRow 48 (has 8 bytes padding per row)
        w, h, bpr = 10, 10, 48
        bgra_data = bytearray()
        for y in range(h):
            for x in range(w):
                bgra_data.extend([50, 100, 150, 255])  # B, G, R, A
            bgra_data.extend([0] * (bpr - w * 4))  # padding

        mock_image = Mock()
        with patch('Quartz.CGImageGetWidth', return_value=w), \
             patch('Quartz.CGImageGetHeight', return_value=h), \
             patch('Quartz.CGImageGetBytesPerRow', return_value=bpr), \
             patch('Quartz.CGImageGetDataProvider', return_value=Mock()), \
             patch('Quartz.CGDataProviderCopyData', return_value=bytes(bgra_data)):
            bgr = _cgimage_to_bgr(mock_image)
            self.assertEqual(bgr.shape, (10, 10, 3))
            self.assertEqual(bgr[0, 0, 0], 50)   # Blue
            self.assertEqual(bgr[0, 0, 1], 100)  # Green
            self.assertEqual(bgr[0, 0, 2], 150)  # Red

    def test_mac_capture_method_connected_state(self):
        capture = MacCaptureMethod()
        self.assertFalse(capture.connected())

        mock_window = Mock()
        mock_window.exists = True
        mock_window.hwnd = 12345
        capture.mac_window = mock_window
        self.assertTrue(capture.connected())

        mock_window.exists = False
        self.assertFalse(capture.connected())

    def test_mac_capture_get_frame_returns_bgr_array(self):
        mock_window = Mock()
        mock_window.exists = True
        mock_window.hwnd = 12345
        mock_window.x = 0
        mock_window.y = 0
        mock_window.width = 1920
        mock_window.height = 1080
        mock_window.scaling = 1.0

        capture = MacCaptureMethod(mac_window=mock_window)
        dummy_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

        with patch('ok.device.capture_methods.mac_capture._cgimage_to_bgr', return_value=dummy_frame), \
             patch('Quartz.CGWindowListCreateImage', return_value=Mock()):
            frame = capture.get_frame()
            self.assertIsNotNone(frame)
            self.assertEqual(frame.shape, (1080, 1920, 3))


class TestMacWindow(unittest.TestCase):
    def test_mac_window_initialization(self):
        exit_event = Mock()
        window = MacWindow(exit_event, title="Wuthering Waves")
        self.assertEqual(window.title, "Wuthering Waves")
        self.assertEqual(window.hwnd, 0)
        self.assertFalse(window.exists)
        self.assertEqual(window.scaling, 1.0)

    def test_mac_window_get_abs_cords(self):
        exit_event = Mock()
        window = MacWindow(exit_event, title="Game")
        window.exists = True
        window.x = 100
        window.y = 200
        window.width = 1920
        window.height = 1080

        screen_x, screen_y = window.get_abs_cords(500, 300)
        self.assertEqual(screen_x, 600)
        self.assertEqual(screen_y, 500)


class TestMacInteraction(unittest.TestCase):
    def test_mac_key_map_contains_common_keys(self):
        self.assertIn('f12', MAC_KEY_MAP)
        self.assertIn('space', MAC_KEY_MAP)
        self.assertIn('return', MAC_KEY_MAP)
        self.assertIn('shift', MAC_KEY_MAP)
        self.assertIn('cmd', MAC_KEY_MAP)
        self.assertEqual(MAC_KEY_MAP['space'], 49)
        self.assertEqual(MAC_KEY_MAP['return'], 36)
        self.assertEqual(MAC_KEY_MAP['escape'], 53)

    def test_accessibility_check_handling(self):
        with patch('ApplicationServices.AXIsProcessTrusted', return_value=True):
            self.assertTrue(_has_accessibility_permissions())

        with patch('ApplicationServices.AXIsProcessTrusted', return_value=False):
            self.assertFalse(_has_accessibility_permissions())

    def test_mac_interaction_move_calls_quartz(self):
        mock_capture = Mock()
        mock_capture.get_abs_cords = Mock(return_value=(300, 400))
        mock_capture.mac_window = Mock(exists=True, is_frontmost=Mock(return_value=True))

        interaction = MacInteraction(mock_capture)
        with patch('ok.device.interaction_methods.mac_interaction.Quartz.CGEventCreateMouseEvent', return_value=Mock()) as create_event, \
             patch('ok.device.interaction_methods.mac_interaction.Quartz.CGEventPost') as post_event:
            interaction.move(100, 200)
            mock_capture.get_abs_cords.assert_called_once_with(100, 200)
            create_event.assert_called_once()
            post_event.assert_called_once()


class TestCursorHelpers(unittest.TestCase):
    def test_cursor_get_and_set(self):
        if sys.platform == 'darwin':
            pos = get_cursor_pos()
            self.assertIsInstance(pos, tuple)
            self.assertEqual(len(pos), 2)
            self.assertIsInstance(pos[0], int)
            self.assertIsInstance(pos[1], int)


class TestMacTitleBar(unittest.TestCase):
    def test_base_window_system_title_bar_rect(self):
        from PySide6.QtCore import QSize, QRect
        from ok.ui.qt.widget.BaseWindow import BaseWindow

        bw = BaseWindow.__new__(BaseWindow)
        bw.isFullScreen = Mock(return_value=False)
        test_size = QSize(1000, 28)

        with patch('sys.platform', 'darwin'):
            rect = bw.systemTitleBarRect(test_size)
            self.assertEqual(rect, QRect(0, 0, 82, 28))
            self.assertEqual(rect.x(), 0)

        with patch('sys.platform', 'win32'):
            rect = bw.systemTitleBarRect(test_size)
            self.assertEqual(rect.x(), 1000 - 75)

    def test_main_window_system_title_bar_rect(self):
        from PySide6.QtCore import QSize, QRect
        from ok.ui.qt.MainWindow import MainWindow

        mw = MainWindow.__new__(MainWindow)
        mw.isFullScreen = Mock(return_value=False)
        test_size = QSize(1200, 28)

        with patch('sys.platform', 'darwin'):
            rect = mw.systemTitleBarRect(test_size)
            self.assertEqual(rect, QRect(0, 0, 82, 28))

    def test_log_window_system_title_bar_rect(self):
        from PySide6.QtCore import QSize, QRect
        from ok.ui.qt.start.LogWindow import LogWindow

        lw = LogWindow.__new__(LogWindow)
        lw.isFullScreen = Mock(return_value=False)
        test_size = QSize(800, 28)

        with patch('sys.platform', 'darwin'):
            rect = lw.systemTitleBarRect(test_size)
            self.assertEqual(rect, QRect(0, 0, 82, 28))

    def test_base_window_set_title_bar_margins(self):
        from ok.ui.qt.widget.BaseWindow import BaseWindow

        bw = BaseWindow.__new__(BaseWindow)
        mock_layout = Mock()
        mock_title_bar = Mock()
        mock_title_bar.hBoxLayout = mock_layout

        with patch('sys.platform', 'darwin'), \
             patch.object(BaseWindow, 'setTitleBar', BaseWindow.setTitleBar), \
             patch('qfluentwidgets.components.widgets.frameless_window.FramelessWindow.setTitleBar'):
            bw.setTitleBar(mock_title_bar)
            mock_layout.setContentsMargins.assert_called_once_with(80, 0, 0, 0)

