"""Run-boundary regressions using synthetic state; no Tk/app initialization or I/O."""
import importlib.util
import logging
from pathlib import Path
import queue
import threading
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def load_owner(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audio = load_owner('videovaudio/run/audio.py', 'audio_run_under_test')
lifecycle = load_owner('videovaudio/run/lifecycle.py', 'run_lifecycle_under_test')


class Harness(audio.AudioRunMixin, lifecycle.RunLifecycleMixin):
    def __init__(self):
        self.folder_queue = ['synthetic-folder']
        self.cancel_requested = False
        self.last_run_summary = {}
        self.is_running = True
        self.active_job_kind = 'audio'
        self.state_lock = threading.Lock()
        self.callbacks = queue.Queue()
        self.logger = Mock(spec=logging.Logger)
        for name in ('problem_log_file', 'summary_log_file', 'report_file', 'log_file',
                     'log_dir', 'process_output_dir'):
            setattr(self, name, 'synthetic-unused')
        for name in ('begin_run_diagnostics', 'log_message', 'start_heartbeat',
                     'update_active_state', 'update_current_session', 'save_run_summary',
                     'finish_active_run', 'update_queue_display', 'set_queue_controls_state',
                     'set_video_settings_state', 'terminate_active_processes',
                     'set_status', 'update_progress'):
            setattr(self, name, Mock())
        self.show_completion_notification = Mock()
        for name in ('btn_start', 'btn_video_start', 'btn_cancel', 'prog_label',
                     'current_folder_label'):
            setattr(self, name, Mock())
        self.now_iso = Mock(return_value='synthetic-time')
        self.reset_run_resource_metrics = Mock(return_value={})
        self.run_resource_metrics_summary = Mock(return_value={})
        self.write_problem = Mock(return_value='synthetic-event')
        self.process_single_folder = Mock(return_value={'outcome': 'success', 'folder': 'synthetic-folder'})
        self.done = Mock(wraps=self.done)

    def ui_after(self, callback):
        self.callbacks.put(callback)


class AudioRunRegressions(unittest.TestCase):
    def setUp(self):
        self.app = Harness()
        self.dialog_patch = patch.object(audio, 'messagebox')
        self.dialogs = self.dialog_patch.start()
        self.addCleanup(self.dialog_patch.stop)

    def execute(self):
        errors = []
        def worker():
            try:
                self.app.process_queue()
            except Exception as error:
                errors.append(error)
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(5)
        self.assertFalse(thread.is_alive(), 'worker must terminate')
        self.assertEqual(errors, [], 'failure must not escape worker')
        self.assertTrue(self.app.is_running, 'UI completion must remain deferred')
        while not self.app.callbacks.empty():
            self.app.callbacks.get_nowait()()
        self.app.done.assert_called_once_with()
        self.assertFalse(self.app.is_running)
        self.app.btn_start.config.assert_called_with(state='normal')
        self.app.btn_video_start.config.assert_called_with(state='normal')

    def assert_failed(self):
        self.assertEqual(self.app.last_run_summary['status'], 'crashed')
        self.assertGreaterEqual(self.app.last_run_summary['failed_count'], 1)
        self.dialogs.showinfo.assert_not_called()
        self.app.update_progress.assert_called_with(100, 'Ошибки')

    def test_begin_failure_restores_ui_without_conversion(self):
        self.app.begin_run_diagnostics.side_effect = OSError('injected startup failure')
        self.execute()
        self.assert_failed()
        self.app.process_single_folder.assert_not_called()
        self.assertEqual(self.app.folder_queue, ['synthetic-folder'])

    def test_session_start_failure_restores_ui_without_conversion(self):
        self.app.update_current_session.side_effect = OSError('injected session failure')
        self.execute()
        self.assert_failed()
        self.app.process_single_folder.assert_not_called()

    def test_failure_report_failure_still_restores_ui(self):
        self.app.begin_run_diagnostics.side_effect = OSError('injected startup failure')
        self.app.write_problem.side_effect = OSError('injected report failure')
        self.execute()
        self.assert_failed()

    def test_active_finalize_failure_suppresses_success_dialog(self):
        self.app.finish_active_run.side_effect = OSError('injected finalization failure')
        self.execute()
        self.assert_failed()
        self.app.process_single_folder.assert_called_once()

    def test_session_finalize_failure_suppresses_success_dialog(self):
        self.app.update_current_session.side_effect = [None, OSError('injected finalization failure')]
        self.execute()
        self.assert_failed()

    def test_success_unchanged(self):
        self.execute()
        self.assertEqual(self.app.last_run_summary['status'], 'completed')
        self.assertEqual(self.app.folder_queue, [])
        self.dialogs.showinfo.assert_not_called()
        self.app.update_progress.assert_called_with(100, '100%')

    def test_failed_start_then_retry_does_not_duplicate_conversion(self):
        self.app.begin_run_diagnostics.side_effect = OSError('injected startup failure')
        self.execute()
        self.assert_failed()
        self.app.begin_run_diagnostics.side_effect = None
        self.app.done.reset_mock()
        self.app.is_running = True
        self.app.last_run_summary = {}
        self.execute()
        self.app.process_single_folder.assert_called_once()
        self.assertEqual(self.app.last_run_summary['status'], 'completed')
        self.dialogs.showinfo.assert_not_called()


if __name__ == '__main__':
    unittest.main()
