"""Active-run state, heartbeat, exception hooks and shutdown lifecycle.

CODEX ROUTE: open this file only when the task matches this responsibility.
Methods are moved whole from the previous owner module; behavior is intentionally unchanged.
"""

import os
import sys
import re
import traceback
import threading
import time
import logging
import hashlib
import faulthandler
from collections import Counter
from datetime import datetime, timezone
import json
import shutil


class DiagnosticsLifecycleMixin:
    def update_active_state(
        self,
        stage=None,
        include_process_details=True,
        **details,
    ):
        """Атомарно обновляет небольшой снимок выполняемой операции."""
        state_file = getattr(self, "active_state_file", "")
        if not state_file:
            return
        self.ensure_diagnostic_io_state()
        with self.active_state_write_lock:
            with self.state_lock:
                if stage:
                    previous_stage = self.active_state.get("stage")
                    if previous_stage != stage:
                        self.active_state["stage_started_monotonic"] = time.monotonic()
                    self.active_state["stage"] = stage
                self.active_state.update(details)
                stage_started = self.active_state.get(
                    "stage_started_monotonic",
                    self.session_started_monotonic,
                )
                self.active_state.update({
                    "schema_version": self.LOG_SCHEMA_VERSION,
                    "app_version": self.APP_VERSION,
                    "session_id": getattr(self, "session_id", ""),
                    "run_id": getattr(self, "current_run_id", ""),
                    "status": self.active_state.get("status", "running"),
                    "updated_at": self.now_iso(),
                    "updated_at_utc": self.utc_now_iso(),
                    "session_elapsed_seconds": max(
                        0,
                        time.monotonic() - self.session_started_monotonic,
                    ),
                    "stage_elapsed_seconds": max(
                        0,
                        time.monotonic() - stage_started,
                    ),
                })
                if include_process_details:
                    self.active_state["process_pid"] = os.getpid()
                    with self.process_lock:
                        process_items = []
                        for process_context in self.process_contexts.values():
                            item = dict(process_context)
                            process_started = item.pop("started_monotonic", None)
                            if isinstance(process_started, (int, float)):
                                item["elapsed_seconds"] = max(
                                    0,
                                    time.monotonic() - process_started,
                                )
                            process_items.append(item)
                    self.active_state["active_processes"] = process_items[:20]
                    self.active_state["active_process_count"] = len(process_items)
                else:
                    self.active_state.pop("process_pid", None)
                    self.active_state.pop("active_processes", None)
                    self.active_state.pop("active_process_count", None)
                snapshot = dict(self.active_state)
                snapshot.pop("stage_started_monotonic", None)
            try:
                retry_count = self.atomic_write_json(state_file, snapshot)
                self.record_diagnostic_retry(
                    "active_state_write_retry",
                    retry_count,
                )
            except Exception as error:
                self.record_diagnostic_failure(
                    "active_state_write_failed",
                    error,
                    file_path=state_file,
                    stage=stage or snapshot.get("stage"),
                )

    def heartbeat_loop(self):
        """Перезаписывает active_run_state.json, не создавая растущий лог."""
        while not self.heartbeat_stop_event.wait(self.HEARTBEAT_INTERVAL_SECONDS):
            current_resources = self.sample_run_resources()
            self.update_active_state(
                system_resources=current_resources,
            )

    def start_heartbeat(self):
        """Запускает один фоновый heartbeat на время очереди."""
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_stop_event.set()
            self.heartbeat_thread.join(timeout=1.0)
            if self.heartbeat_thread.is_alive():
                return
        self.heartbeat_stop_event.clear()
        self.heartbeat_thread = threading.Thread(
            target=self.heartbeat_loop,
            name="diagnostics-heartbeat",
            daemon=True,
        )
        self.heartbeat_thread.start()

    def stop_heartbeat(self):
        """Останавливает heartbeat до записи окончательного состояния."""
        self.heartbeat_stop_event.set()
        thread = self.heartbeat_thread
        if (
            thread
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(timeout=2.0)
        if thread and not thread.is_alive():
            self.heartbeat_thread = None

    def clear_active_transient_state(self):
        """Убирает временные пути и PID после завершения, оставляя краткий итог."""
        with self.state_lock:
            previous = dict(self.active_state)
            last_completed_folder = {
                "folder": previous.get("folder"),
                "folder_status": previous.get("folder_status"),
                "folder_elapsed_seconds": previous.get(
                    "folder_elapsed_seconds"
                ),
            }
            last_completed_folder = {
                key: value
                for key, value in last_completed_folder.items()
                if value is not None
            }
            preserved = {
                key: previous.get(key)
                for key in (
                    "queue_total",
                    "folder_index",
                    "folder_total",
                )
                if previous.get(key) is not None
            }
            if last_completed_folder:
                preserved["last_completed_folder"] = (
                    last_completed_folder
                )
            self.active_state = preserved

    def finish_active_run(self, status, **details):
        """Фиксирует терминальное состояние и останавливает heartbeat."""
        self.stop_heartbeat()
        self.clear_active_transient_state()
        self.update_active_state(
            "finished",
            include_process_details=False,
            status=status,
            finished_at=self.now_iso(),
            finished_at_utc=self.utc_now_iso(),
            **details,
        )

    def install_exception_hooks(self):
        """Ловит необработанные ошибки главного, Tkinter и рабочих потоков."""
        self.original_sys_excepthook = sys.excepthook
        self.original_threading_excepthook = getattr(
            threading,
            "excepthook",
            None,
        )

        def record_exception(kind, exc_type, exc_value, exc_traceback, **extra):
            try:
                self.write_problem(
                    kind,
                    "Необработанное исключение перехвачено глобальной диагностикой.",
                    severity="critical",
                    exception=f"{getattr(exc_type, '__name__', exc_type)}: {exc_value}",
                    traceback="".join(
                        traceback.format_exception(
                            exc_type,
                            exc_value,
                            exc_traceback,
                        )
                    ),
                    **extra,
                )
                self.update_active_state(
                    "unhandled_exception",
                    status="crashed",
                    exception_kind=kind,
                )
            except Exception:
                pass

        def sys_hook(exc_type, exc_value, exc_traceback):
            record_exception(
                "unhandled_main_exception",
                exc_type,
                exc_value,
                exc_traceback,
            )
            if self.original_sys_excepthook:
                self.original_sys_excepthook(
                    exc_type,
                    exc_value,
                    exc_traceback,
                )

        def thread_hook(args):
            record_exception(
                "unhandled_thread_exception",
                args.exc_type,
                args.exc_value,
                args.exc_traceback,
                thread_name=getattr(args.thread, "name", ""),
            )
            if self.original_threading_excepthook:
                self.original_threading_excepthook(args)

        def tk_hook(exc_type, exc_value, exc_traceback):
            record_exception(
                "unhandled_tk_callback_exception",
                exc_type,
                exc_value,
                exc_traceback,
            )

        sys.excepthook = sys_hook
        if hasattr(threading, "excepthook"):
            threading.excepthook = thread_hook
        self.root.report_callback_exception = tk_hook

        try:
            self.crash_log_handle = open(
                self.crash_log_file,
                "a",
                encoding="utf-8",
            )
            self.crash_log_handle.write(
                f"\n=== FAULTHANDLER SESSION {self.session_id} {self.now_iso()} ===\n"
            )
            self.crash_log_handle.flush()
            self.crash_log_initial_size = os.path.getsize(
                self.crash_log_file
            )
            faulthandler.enable(file=self.crash_log_handle, all_threads=True)
        except Exception as e:
            try:
                self.logger.warning(
                    "FAULTHANDLER_SETUP_FAILED %s: %s",
                    type(e).__name__,
                    e,
                )
            except Exception:
                pass

    def on_close(self):
        """Корректно помечает обычное закрытие, чтобы не спутать его с падением."""
        try:
            if getattr(self, "is_running", False):
                self.request_cancel()
                close_status = "cancelled_by_window_close"
                self.finish_active_run(close_status)
            else:
                close_status = "closed_by_user"
                self.stop_heartbeat()
                self.clear_active_transient_state()
                self.update_active_state(
                    "closed",
                    include_process_details=False,
                    status=close_status,
                    application_status=close_status,
                    last_run_status=(
                        getattr(self, "last_run_summary", {}) or {}
                    ).get("status"),
                    closed_at=self.now_iso(),
                    closed_at_utc=self.utc_now_iso(),
                )
            try:
                self.update_current_session(
                    getattr(self, "last_run_summary", {}) or {
                        "status": close_status,
                    }
                )
            except Exception as error:
                try:
                    self.logger.warning(
                        "CURRENT_SESSION_CLOSE_FAILED %s: %s",
                        type(error).__name__,
                        error,
                    )
                except Exception:
                    pass
            self.terminate_active_processes()
        finally:
            try:
                if self.crash_log_handle:
                    try:
                        faulthandler.disable()
                    except Exception:
                        pass
                    self.crash_log_handle.flush()
                    self.crash_log_handle.close()
            except Exception:
                pass
            try:
                if (
                    self.crash_log_initial_size
                    and os.path.isfile(self.crash_log_file)
                    and os.path.getsize(self.crash_log_file)
                    <= self.crash_log_initial_size
                ):
                    os.remove(self.crash_log_file)
            except OSError:
                pass
            self.root.destroy()
