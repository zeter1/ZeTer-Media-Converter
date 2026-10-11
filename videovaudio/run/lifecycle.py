"""Shared run completion/UI restoration.

CODEX ROUTE: open this file only when the task matches this responsibility.
Methods are moved whole from the previous owner module; behavior is intentionally unchanged.
"""

import os
import traceback
from tkinter import messagebox
import threading
import time
import uuid
from datetime import datetime
from shutil import which


class RunLifecycleMixin:
    def done(self):
        self.btn_start.config(state="normal")
        self.btn_video_start.config(state="normal")
        self.btn_cancel.config(state="disabled")
        self.set_queue_controls_state("normal")
        self.set_video_settings_state(True)
        self.is_running = False
        self.active_job_kind = None
        self.terminate_active_processes()

        summary = getattr(self, "last_run_summary", {}) or {}
        if summary.get("cancelled"):
            self.prog_label.config(text="Отмена")
            self.set_status("Отменено пользователем")
        elif summary.get("failed_count", 0) > 0:
            self.update_progress(100, "Ошибки")
            self.set_status("Завершено с ошибками — смотри Логи проблем")
        else:
            self.update_progress(100, "100%")
            self.set_status("Готов к новой задаче ✓")

        self.current_folder_label.config(text="Текущая папка: нет")
        if not summary.get('cancelled') and summary.get('status') in (
            'completed', 'completed_with_skips', 'completed_with_errors'
        ):
            files = tuple(
                output['file']
                for result in summary.get('folders', ())
                if result.get('outcome') == 'success'
                for output in result.get('output_files', ())
                if output.get('file')
            )
            if files:
                self.show_completion_notification(files)
