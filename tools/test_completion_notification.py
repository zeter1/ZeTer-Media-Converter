"""Completion routing tests; synthetic files, no application initialization/logs."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from test_audio_run_regressions import Harness

GUI = '--gui' in sys.argv
if GUI:
    sys.argv.remove('--gui')


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.app = Harness()
        self.temp = tempfile.TemporaryDirectory(prefix='completion-')
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / 'Курс с пробелами.mp3'
        self.file.write_bytes(b'synthetic result')
        self.result = {'outcome': 'success', 'folder': self.temp.name,
                       'output_files': [{'file': str(self.file)}]}

    def test_finished_run_delivers_exact_published_files(self):
        self.app.last_run_summary = {'status': 'completed', 'folders': [self.result]}
        self.app.done()
        self.app.show_completion_notification.assert_called_once_with((str(self.file),))
        self.assertFalse(self.app.is_running)

    def test_failed_skipped_and_cancelled_results_are_not_announced(self):
        for outcome in ('failed', 'skipped', 'cancelled'):
            with self.subTest(outcome=outcome):
                self.app.last_run_summary = {'status': 'completed', 'folders': [
                    dict(self.result, outcome=outcome)]}
                self.app.done()
        self.app.show_completion_notification.assert_not_called()

    def test_cancelled_or_crashed_run_does_not_announce_success(self):
        for status in ('cancelled', 'crashed'):
            self.app.last_run_summary = {'status': status, 'folders': [self.result]}
            self.app.done()
        self.app.show_completion_notification.assert_not_called()

    def test_partial_success_only_announces_successful_output(self):
        self.app.last_run_summary = {'status': 'completed_with_errors', 'failed_count': 1,
                                    'folders': [self.result, dict(self.result, outcome='failed')]}
        self.app.done()
        self.app.show_completion_notification.assert_called_once_with((str(self.file),))

    def test_explorer_receives_unicode_path_as_single_argument(self):
        from videovaudio import notifications
        with patch.object(notifications.subprocess, 'Popen') as launch:
            notifications.reveal_file(str(self.file))
        selected_path = Path(launch.call_args.args[0][-1])
        # Windows can expand an 8.3 temp path (RUNNER~1) during resolve().
        # Explorer must select the same file, not preserve the path spelling.
        self.assertTrue(selected_path.samefile(self.file))
        self.assertEqual(selected_path.name, self.file.name)
        self.assertEqual(launch.call_args.args[0][-2], '/select,')
        self.assertFalse(launch.call_args.kwargs.get('shell', False))

    def test_missing_output_does_not_launch_explorer(self):
        from videovaudio import notifications
        self.file.unlink()
        with patch.object(notifications.subprocess, 'Popen') as launch:
            with self.assertRaises(FileNotFoundError):
                notifications.reveal_file(str(self.file))
        launch.assert_not_called()


@unittest.skipUnless(GUI, 'use --gui for an isolated native Tk window')
class NativeWindowTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from videovaudio.notifications import CompletionNotification
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.notice = CompletionNotification(self.root)
        self.temp = tempfile.TemporaryDirectory(prefix='notification-gui-')
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / 'Курс с пробелами.mp3'
        self.file.write_bytes(b'synthetic')
        self.notice.show((str(self.file),))
        self.root.update()

    def test_persistent_topmost_window_survives_hidden_root_and_navigation(self):
        from videovaudio.notifications import work_area
        window = self.notice.window
        self.assertTrue(window.attributes('-topmost'))
        self.assertTrue(window.overrideredirect())
        self.assertTrue(window.winfo_viewable())
        left, top, right, bottom = work_area(self.root)
        self.assertGreaterEqual(window.winfo_rootx(), left)
        self.assertGreaterEqual(window.winfo_rooty(), top)
        self.assertEqual(window.winfo_rootx() + window.winfo_width(), right - 12)
        self.assertEqual(window.winfo_rooty() + window.winfo_height(), bottom - 12)
        self.root.after(1200, self.root.quit)
        self.root.mainloop()
        self.assertTrue(window.winfo_viewable(), 'notification must not expire')
        with patch('videovaudio.notifications.reveal_file') as reveal:
            row = self.notice.items.winfo_children()[0]
            button = next(child for child in row.winfo_children()
                          if child.winfo_class() == 'TButton')
            button.invoke()
            reveal.assert_called_once_with(str(self.file))
        self.assertTrue(window.winfo_viewable(), 'navigation must not dismiss it')
        window.event_generate('<Escape>')
        self.root.update()
        self.assertTrue(window.winfo_exists())
        window.tk.call(window.protocol('WM_DELETE_WINDOW'))
        self.assertTrue(window.winfo_exists())

    def test_repeated_run_missing_file_close_and_reopen(self):
        window = self.notice.window
        self.notice.show((str(self.file), str(self.file)))
        self.root.update()
        self.assertIs(window, self.notice.window)
        self.assertEqual(len(self.notice.items.winfo_children()), 3)
        self.file.unlink()
        self.notice.open_file(str(self.file))
        self.assertTrue(self.notice.error.cget('text'))
        self.assertTrue(window.winfo_viewable())
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        cross = next(child for child in descendants(window)
                     if child.winfo_class() == 'TButton' and child.cget('text') == '✕')
        cross.invoke()
        self.assertFalse(window.winfo_exists())
        self.assertIsNone(self.notice.window)
        self.file.write_bytes(b'new synthetic result')
        self.notice.show((str(self.file),))
        self.root.update()
        self.assertTrue(self.notice.window.winfo_viewable())
        self.assertEqual(len(self.notice.items.winfo_children()), 1)

    def test_many_outputs_keep_order_and_scroll_without_overlapping_windows(self):
        paths = tuple(str(Path(self.temp.name) / f'Часть {i:02d}.mp3') for i in range(20))
        self.notice.show(paths)
        self.root.update()
        rows = self.notice.items.pack_slaves()
        self.assertEqual([row.winfo_children()[0].cget('text') for row in rows[:20]],
                         [Path(path).name for path in paths])
        self.assertGreater(self.notice.items.winfo_height(), self.notice.canvas.winfo_height())
        self.notice.canvas.yview_moveto(1)
        self.root.update()
        self.assertGreater(self.notice.canvas.yview()[0], 0)
        self.assertEqual(len([w for w in self.root.winfo_children()
                              if w.winfo_class() == 'Toplevel']), 1)

    def test_monitor_to_the_left_uses_absolute_negative_coordinates(self):
        with patch('videovaudio.notifications.work_area', return_value=(-1920, 0, 0, 1080)):
            self.notice.show((str(self.file),))
        self.root.update()
        self.assertEqual(self.notice.window.winfo_rootx(), -472)
        self.assertEqual(self.notice.window.winfo_rooty(), 698)


if __name__ == '__main__':
    unittest.main()
