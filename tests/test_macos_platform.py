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
        with patch('Quartz.CGWindowListCopyWindowInfo', return_value=[]):
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
        self.assertEqual(MAC_KEY_MAP['f2'], 120)
        self.assertEqual(MAC_KEY_MAP['a'], 0)
        self.assertEqual(MAC_KEY_MAP['w'], 13)
        self.assertEqual(MAC_KEY_MAP['s'], 1)
        self.assertEqual(MAC_KEY_MAP['d'], 2)
        self.assertEqual(MAC_KEY_MAP['e'], 14)
        self.assertEqual(MAC_KEY_MAP['q'], 12)
        self.assertEqual(MAC_KEY_MAP['r'], 15)
        self.assertEqual(MAC_KEY_MAP['b'], 11)
        self.assertEqual(MAC_KEY_MAP['m'], 46)

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

    def test_send_key_a_and_f2(self):
        mock_capture = Mock()
        mock_capture.mac_window = Mock(exists=True, is_frontmost=Mock(return_value=True))
        interaction = MacInteraction(mock_capture)

        with patch('Quartz.CGEventCreateKeyboardEvent', return_value=Mock()) as mock_create_event, \
             patch('Quartz.CGEventPost') as mock_post_event, \
             patch.object(interaction, '_ensure_permissions', return_value=True):
            # 'a' has keycode 0, must NOT be ignored
            interaction.send_key('a')
            mock_create_event.assert_any_call(None, 0, True)
            mock_create_event.assert_any_call(None, 0, False)

            # 'f2' has keycode 120
            interaction.send_key('f2')
            mock_create_event.assert_any_call(None, 120, True)
            mock_create_event.assert_any_call(None, 120, False)

    def test_send_key_combo_fn_f2(self):
        mock_capture = Mock()
        mock_capture.mac_window = Mock(exists=True, is_frontmost=Mock(return_value=True))
        interaction = MacInteraction(mock_capture)

        mock_event = Mock()
        with patch('Quartz.CGEventCreateKeyboardEvent', return_value=mock_event) as mock_create_event, \
             patch('Quartz.CGEventSetFlags') as mock_set_flags, \
             patch('Quartz.CGEventGetFlags', return_value=0), \
             patch('Quartz.CGEventPost'), \
             patch.object(interaction, '_ensure_permissions', return_value=True):
            # 'fn+f2': fn (keycode 63), f2 (keycode 120)
            interaction.send_key('fn+f2')
            # Check fn pressed & released (63)
            mock_create_event.assert_any_call(None, 63, True)
            mock_create_event.assert_any_call(None, 63, False)
            # Check f2 pressed & released (120)
            mock_create_event.assert_any_call(None, 120, True)
            mock_create_event.assert_any_call(None, 120, False)
            # Check that SecondaryFn flag was set
            mock_set_flags.assert_called()


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

    def test_start_tab_macos_device_label(self):
        from ok.ui.qt.start.StartTab import StartTab

        tab = StartTab.__new__(StartTab)
        tab.tr = lambda s: "Mac版" if s == "Mac" else ("已断开" if s == "Disconnected" else s)
        tab.device_list_row = -1
        tab.device_list = Mock()
        tab.device_list.count.return_value = 0
        tab.filter_devices = Mock()
        tab.start_card = Mock()
        tab.capture_list = Mock()
        tab.interaction_list = Mock()
        tab.logger = Mock()

        mac_device = {
            'address': '',
            'imei': 'mac',
            'device': 'macos',
            'nick': 'Wuthering Waves',
            'connected': False,
            'resolution': '0x0'
        }

        with patch('ok.og.device_manager') as mock_dm:
            mock_dm.get_devices.return_value = [mac_device]
            mock_dm.config = {'preferred': 'mac'}
            tab.update_capture(finished=False)

            tab.device_list.addItem.assert_called_once()
            added_item = tab.device_list.addItem.call_args[0][0]
            self.assertIn("Mac版 已断开: Wuthering Waves", added_item.text())

    def test_select_capture_list_view_macos(self):
        from ok.ui.qt.start.SelectCaptureListView import SelectCaptureListView

        view = SelectCaptureListView.__new__(SelectCaptureListView)
        view.count = Mock(return_value=0)
        view.addItem = Mock()
        view.blockSignals = Mock()
        view.setCurrentRow = Mock()
        view.tr = lambda s: "Mac原生截图" if s == "MacCapture" else s

        mac_device = {'device': 'macos'}

        with patch('ok.og.device_manager') as mock_dm:
            mock_dm.get_preferred_device.return_value = mac_device
            mock_dm.mac_config = {'capture_method': ['MacCapture']}
            mock_dm.get_preferred_capture.return_value = 'MacCapture'

            view.update_for_device()
            view.addItem.assert_called()
            added_item = view.addItem.call_args[0][0]
            self.assertEqual(added_item.text(), "Mac原生截图")

    def test_select_interaction_list_view_macos(self):
        from ok.ui.qt.start.SelectInteractionListView import SelectInteractionListView

        view = SelectInteractionListView.__new__(SelectInteractionListView)
        view.count = Mock(return_value=0)
        view.addItem = Mock()
        view.blockSignals = Mock()
        view.setCurrentRow = Mock()
        view.tr = lambda s: "Mac原生交互" if s == "Mac" else s

        mac_device = {'device': 'macos'}

        with patch('ok.og.device_manager') as mock_dm:
            mock_dm.get_preferred_device.return_value = mac_device
            mock_dm.mac_config = {'interaction': ['Mac']}
            mock_dm.config = {'interaction': 'Mac'}

            view.update_for_device()
            view.addItem.assert_called()
            added_item = view.addItem.call_args[0][0]
            self.assertEqual(added_item.text(), "Mac原生交互")

    def test_find_game_window_chinese_and_process_names(self):
        import threading
        from ok.device.capture_methods.mac_window import MacWindow
        exit_event = threading.Event()
        window = MacWindow(exit_event=exit_event, title="Wuthering Waves", exe_names=["Wuthering Waves.app"])

        sample_windows = [
            {'kCGWindowNumber': 101, 'kCGWindowOwnerName': '鸣潮', 'kCGWindowName': '',
             'kCGWindowBounds': {'X': 0, 'Y': 0, 'Width': 1920, 'Height': 1080}},
            {'kCGWindowNumber': 102, 'kCGWindowOwnerName': 'Client-Mac-Shipping', 'kCGWindowName': 'Main',
             'kCGWindowBounds': {'X': 0, 'Y': 0, 'Width': 1920, 'Height': 1080}},
            {'kCGWindowNumber': 103, 'kCGWindowOwnerName': 'SystemUIServer', 'kCGWindowName': '',
             'kCGWindowBounds': {'X': 0, 'Y': 0, 'Width': 30, 'Height': 30}},
        ]

        with patch('ok.device.capture_methods.mac_window.Quartz.CGWindowListCopyWindowInfo', return_value=sample_windows):
            wid, bounds, owner = window._find_game_window()
            self.assertEqual(wid, 101)
            self.assertEqual(owner, '鸣潮')

    def test_device_manager_get_mac_app_path(self):
        from ok.device.DeviceManager import DeviceManager
        dm = DeviceManager.__new__(DeviceManager)
        dm.mac_config = {'bundle_id': ['com.kurogame.mingchao']}

        with patch('os.path.exists', side_effect=lambda p: p == '/Applications/鸣潮.app'):
            app_path = dm.get_mac_app_path()
            self.assertEqual(app_path, '/Applications/鸣潮.app')

    def test_device_manager_get_exe_path_macos(self):
        from ok.device.DeviceManager import DeviceManager
        dm = DeviceManager.__new__(DeviceManager)
        dm.get_mac_app_path = Mock(return_value='/Applications/鸣潮.app')
        device = {'device': 'macos', 'full_path': '/Applications/鸣潮.app'}
        self.assertEqual(dm.get_exe_path(device), '/Applications/鸣潮.app')

    def test_process_execute_macos(self):
        from ok.util.process import execute
        with patch('sys.platform', 'darwin'), \
             patch('os.path.exists', return_value=True), \
             patch('subprocess.Popen') as mock_popen:
            success = execute('/Applications/鸣潮.app')
            self.assertTrue(success)
            mock_popen.assert_called_once_with(['open', '/Applications/鸣潮.app'])

    def test_start_controller_check_mac_permissions(self):
        from ok.core.start_controller import StartController
        sc = StartController.__new__(StartController)
        sc.tr = lambda s: s

        mock_quartz = Mock()
        mock_quartz.CGPreflightScreenCaptureAccess.return_value = False

        with patch('sys.platform', 'darwin'), \
             patch.dict('sys.modules', {'Quartz': mock_quartz}):
            # Passive check (request=False) should not prompt
            err_passive = sc.check_mac_permissions(request=False)
            self.assertIn("屏幕录制权限", err_passive)
            mock_quartz.CGRequestScreenCaptureAccess.assert_not_called()

            # Active check (request=True) prompts once
            err = sc.check_mac_permissions(request=True)
            self.assertIn("屏幕录制权限", err)
            mock_quartz.CGRequestScreenCaptureAccess.assert_called_once()

            # Subsequent active check should NOT prompt again
            err2 = sc.check_mac_permissions(request=True)
            self.assertIn("屏幕录制权限", err2)
            mock_quartz.CGRequestScreenCaptureAccess.assert_called_once()

    def test_start_controller_check_mac_accessibility_permissions(self):
        from ok.core.start_controller import StartController
        sc = StartController.__new__(StartController)
        sc.tr = lambda s: s

        mock_quartz = Mock()
        mock_quartz.CGPreflightScreenCaptureAccess.return_value = True

        mock_as = Mock()
        mock_as.AXIsProcessTrusted.return_value = False
        mock_as.kAXTrustedCheckOptionPrompt = 'AXTrustedCheckOptionPrompt'

        with patch('sys.platform', 'darwin'), \
             patch.dict('sys.modules', {'Quartz': mock_quartz, 'ApplicationServices': mock_as}):
            # Passive check should not prompt
            err_passive = sc.check_mac_permissions(request=False)
            self.assertIn("辅助功能权限", err_passive)
            mock_as.AXIsProcessTrustedWithOptions.assert_not_called()

            # Active check should prompt once
            err = sc.check_mac_permissions(request=True)
            self.assertIn("辅助功能权限", err)
            mock_as.AXIsProcessTrustedWithOptions.assert_called_once()

            # Subsequent check should not prompt again
            err2 = sc.check_mac_permissions(request=True)
            self.assertIn("辅助功能权限", err2)
            mock_as.AXIsProcessTrustedWithOptions.assert_called_once()

    def test_capture_method_placeholders_safe_for_isinstance(self):
        from ok.device.capture import BrowserCaptureMethod, BitBltCaptureMethod, DesktopDuplicationCaptureMethod
        self.assertIsNotNone(BrowserCaptureMethod)
        self.assertIsNotNone(BitBltCaptureMethod)
        self.assertFalse(isinstance(object(), BrowserCaptureMethod))
        self.assertFalse(isinstance(MacCaptureMethod(), BrowserCaptureMethod))
        self.assertFalse(isinstance(MacCaptureMethod(), BitBltCaptureMethod))

    def test_get_path_relative_to_exe_finds_bundle_resources(self):
        import tempfile
        from pathlib import Path
        from ok.util.file import get_path_relative_to_exe

        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle_dir = Path(tmp_dir) / "MyApp.app" / "Contents"
            macos_dir = bundle_dir / "MacOS"
            resources_dir = bundle_dir / "Resources"
            macos_dir.mkdir(parents=True)
            resources_dir.mkdir(parents=True)

            mock_exe = macos_dir / "myapp"
            mock_exe.touch()
            target_res = resources_dir / "i18n" / "zh_CN"
            target_res.mkdir(parents=True)

            with patch('sys.frozen', True, create=True), \
                 patch('sys.executable', str(mock_exe)):
                found = get_path_relative_to_exe("i18n", "zh_CN")
                self.assertEqual(found, str(target_res))

    def test_explorer_dispatch_macos(self):
        from pathlib import Path
        from ok.util.explorer import open_explorer_folder, reveal_in_explorer
        with patch('sys.platform', 'darwin'), \
             patch('subprocess.Popen') as mock_popen:
            open_explorer_folder('/tmp')
            mock_popen.assert_called_with(['open', str(Path('/tmp').resolve())])

            test_file = Path('/tmp/test.log')
            with patch('pathlib.Path.exists', return_value=True):
                reveal_in_explorer(str(test_file))
                mock_popen.assert_called_with(['open', '-R', str(test_file.resolve())])

    def test_windows_schedule_safe_on_macos(self):
        from ok.util.windows_schedule import WindowsScheduleManager
        with patch('sys.platform', 'darwin'):
            manager = WindowsScheduleManager(config={"gui_title": "OK-Test"})
            manager._init_com_service()
            self.assertIsNone(manager.SCHEDULE_SERVICE)
            self.assertEqual(manager._query_tasks_via_schtasks(), [])
            self.assertFalse(manager._create_task_via_schtasks("test", 1, Mock(), True, "\\path"))
            self.assertFalse(manager._delete_task_by_path("\\path"))
            self.assertFalse(manager._set_task_enabled("\\path", True))

    def test_mac_window_filters_helper_app(self):
        exit_event = Mock()
        window = MacWindow(exit_event, title=["Wuthering Waves", "鸣潮"])
        mock_window_list = [
            # Helper app window (OK-WW) - must be ignored!
            {
                'kCGWindowNumber': 9999,
                'kCGWindowOwnerName': '鸣潮小助手',
                'kCGWindowName': '',
                'kCGWindowOwnerPID': 18152,
                'kCGWindowBounds': {'X': 100, 'Y': 100, 'Width': 1200, 'Height': 800},
            },
            # Real game window
            {
                'kCGWindowNumber': 5750,
                'kCGWindowOwnerName': '鸣潮',
                'kCGWindowName': '',
                'kCGWindowOwnerPID': 18136,
                'kCGWindowBounds': {'X': 0, 'Y': 0, 'Width': 640, 'Height': 432},
            }
        ]
        with patch('Quartz.CGWindowListCopyWindowInfo', return_value=mock_window_list):
            win_id, bounds, owner = window._find_game_window()
            self.assertEqual(win_id, 5750)
            self.assertEqual(owner, '鸣潮')
            self.assertEqual(window.game_pid, 18136)

    def test_mac_window_bring_to_front_pid_activation(self):
        exit_event = Mock()
        window = MacWindow(exit_event, title="Game")
        window.exists = True
        window.game_pid = 18136

        mock_ns_app = Mock()
        mock_app = Mock()
        mock_ns_app.runningApplicationWithProcessIdentifier_.return_value = mock_app
        with patch('ok.device.capture_methods.mac_window.NSRunningApplication', mock_ns_app):
            success = window.bring_to_front()
            self.assertTrue(success)
            mock_ns_app.runningApplicationWithProcessIdentifier_.assert_called_once_with(18136)
            mock_app.activateWithOptions_.assert_called_once_with(2)

    def test_mac_interaction_permission_throttling(self):
        mock_capture = Mock()
        interaction = MacInteraction(mock_capture)
        with patch('ok.device.interaction_methods.mac_interaction._has_accessibility_permissions', return_value=False), \
             patch('ok.device.interaction_methods.mac_interaction.logger.warning') as mock_log:
            # First call logs warning
            self.assertFalse(interaction._ensure_permissions())
            self.assertEqual(mock_log.call_count, 1)

            # Immediate second call should be throttled (no duplicate log)
            self.assertFalse(interaction._ensure_permissions())
            self.assertEqual(mock_log.call_count, 1)

    def test_calculate_title_bar_height_for_16_10(self):
        exit_event = Mock()
        window = MacWindow(exit_event, title="Game")
        # 640x432 with 32pt title bar gives 640x400 (16:10)
        tb = window._calculate_title_bar_height(640, 432)
        self.assertEqual(tb, 32)

        # Already 16:10 or 16:9 -> no title bar deduction
        self.assertEqual(window._calculate_title_bar_height(640, 400), 0)
        self.assertEqual(window._calculate_title_bar_height(1280, 720), 0)

    def test_mac_window_coordinates_with_title_bar(self):
        exit_event = Mock()
        window = MacWindow(exit_event, title="Game")
        window.x = 100
        window.y = 50
        window.title_bar_height = 32
        window.scaling = 2.0

        # Game-relative (200, 100) -> on Retina 2x: dx = 100, dy = 50
        # Absolute coords should add title_bar_height to Y:
        # X: 100 + 100 = 200, Y: 50 + 32 + 50 = 132
        abs_x, abs_y = window.get_abs_cords(200, 100)
        self.assertEqual(abs_x, 200)
        self.assertEqual(abs_y, 132)

    def test_mac_capture_crops_title_bar_when_window_captured(self):
        mock_window = Mock()
        mock_window.exists = True
        mock_window.visible = True
        mock_window.x = 0
        mock_window.y = 0
        mock_window.width = 640
        mock_window.height = 400
        mock_window.hwnd = 1001
        mock_window.title_bar_height = 32
        mock_window.scaling = 2.0

        capture = MacCaptureMethod(mac_window=mock_window)
        import numpy as np
        # Simulate 1280x864 image (Retina 640x432)
        raw_image = np.zeros((864, 1280, 3), dtype=np.uint8)

        with patch('Quartz.CGWindowListCreateImage', return_value=Mock()), \
             patch('ok.device.capture_methods.mac_capture._cgimage_to_bgr', return_value=raw_image):
            frame = capture.do_get_frame()
            self.assertIsNotNone(frame)
            # 864 - (32 * 2) = 800
            self.assertEqual(frame.shape, (800, 1280, 3))

    def test_multi_aspect_ratio_validation(self):
        from ok.util.window import ratio_text_to_number
        from ok.util.collection import parse_ratio

        # List of string ratios
        ratios = ratio_text_to_number(['16:9', '16:10'])
        self.assertAlmostEqual(ratios[0], 16 / 9, places=3)
        self.assertAlmostEqual(ratios[1], 16 / 10, places=3)

        parsed = parse_ratio(['16:9', '16:10'])
        self.assertEqual(len(parsed), 2)

        # Test TaskExecutor check_frame_and_resolution with 16:10 frame
        from ok.task.TaskExecutor import TaskExecutor
        executor = TaskExecutor.__new__(TaskExecutor)
        executor.device_manager = Mock()
        import numpy as np
        frame_16_10 = np.zeros((800, 1280, 3), dtype=np.uint8)
        mock_method = Mock()
        mock_method.width = 1280
        mock_method.height = 800
        mock_method.get_frame.return_value = frame_16_10
        executor.device_manager.capture_method = mock_method

        support, res_str = executor.check_frame_and_resolution(['16:9', '16:10'], min_size=(1280, 720))
        self.assertTrue(support)
        self.assertEqual(res_str, '1280x800')

