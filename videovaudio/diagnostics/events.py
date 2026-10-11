"""Structured problem events, deduplication and recovery linkage.

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


class ProblemEventsMixin:
    def problem_guidance(self, kind):
        """Единые пояснения, чтобы Codex видел влияние и следующий шаг."""
        guidance = {
            "input_skipped_no_audio": {
                "impact": "Файл не попал в аудио, остальные исправные видео продолжают обрабатываться.",
                "likely_cause": "В видео отсутствует звуковая дорожка.",
                "codex_action": "Считать это корректным пропуском, а не сбоем всей папки.",
            },
            "folder_skipped_no_media": {
                "impact": "Папка не требует конвертации и не считается ошибочной.",
                "likely_cause": "В папке нет файлов поддерживаемых видеоформатов.",
                "codex_action": "Показать папку в разделе ожидаемых пропусков и продолжить очередь.",
            },
            "media_file_skipped": {
                "impact": "Один проблемный файл пропущен, обработка хороших видео продолжается.",
                "likely_cause": "Файл повреждён, недоступен или не поддерживается FFmpeg.",
                "codex_action": "Использовать diagnosis и diagnostic_excerpt для точной классификации.",
            },
            "libmp3lame_joint_stereo_assertion_retry": {
                "impact": "Первый MP3 не публикуется; файл повторно кодируется в совместимом режиме.",
                "likely_cause": "Внутренний сбой joint-stereo режима libmp3lame на конкретных аудиоданных.",
                "codex_action": "Повторить без joint stereo, сохранить временную шкалу и проверить длительность MP3.",
            },
            "folder_completed_with_skips": {
                "impact": "Итоговое аудио создано только из исправных видео; перечисленные файлы отсутствуют.",
                "likely_cause": "В папке были отдельные проблемные или беззвучные видео.",
                "codex_action": "Проверить причины пропусков и не считать успешные файлы потерянными.",
            },
            "concat_duration_mismatch_retry_transcode": {
                "impact": "Быстрый результат отклонён до публикации; запускается корректирующая склейка.",
                "likely_cause": "Concat copy сохранил разрывы или некорректные временные метки MP3.",
                "codex_action": "Проверить величину расхождения и предупреждения о DTS/PTS.",
            },
            "concat_duration_mismatch_after_fallback": {
                "impact": "Итог не публикуется, потому что длительность недостоверна.",
                "likely_cause": "Даже повторная склейка не восстановила непрерывную временную шкалу.",
                "codex_action": "Исследовать конкретные входные MP3 и их временные метки.",
            },
            "output_audio_profile_mismatch": {
                "impact": "Отдельный MP3 не соответствует единому профилю склейки.",
                "likely_cause": "FFmpeg не применил заданную частоту дискретизации или число каналов.",
                "codex_action": "Проверить фактический профиль, команду конвертации и версию FFmpeg.",
            },
            "split_copy_duration_too_long_retry_transcode": {
                "impact": "Неточный быстрый фрагмент заменяется точным перекодированным.",
                "likely_cause": "Разрезание MP3 по пакетам дало погрешность больше допустимой.",
                "codex_action": "Считать событие восстановленным, если fallback завершился успешно.",
            },
            "process_timeout": {
                "impact": "Один процесс остановлен по таймауту и его файл будет пропущен.",
                "likely_cause": "Повреждённый файл, медленный диск или зависание FFmpeg.",
                "codex_action": "Сопоставить размер файла, этап, время и diagnostic_excerpt.",
            },
        }
        return guidance.get(kind, {
            "impact": "Событие может влиять на полноту или корректность результата.",
            "likely_cause": "Причина определяется по полям события и diagnostic_excerpt.",
            "codex_action": "Проверить этап, пути, код возврата и ближайшие связанные события.",
        })

    def sanitize_problem_value(self, value, key="", depth=0):
        """Не даёт одной ошибке раздуть JSONL до мегабайт."""
        if depth > 4:
            return "[слишком глубокая структура]"
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            lowered_key = key.lower()
            if any(secret in lowered_key for secret in ("password", "token", "api_key", "secret")):
                return "[СКРЫТО]"
            if any(name in lowered_key for name in (
                "stderr",
                "stdout",
                "output_tail",
                "diagnostic_excerpt",
                "process_output",
            )):
                return self.diagnostic_excerpt(value)
            limit = self.MAX_PROBLEM_TEXT_CHARS
            return self.trim_text(value, limit, keep_tail=lowered_key == "traceback")
        if isinstance(value, dict):
            items = list(value.items())
            result = {
                str(child_key): self.sanitize_problem_value(child_value, str(child_key), depth + 1)
                for child_key, child_value in items[:40]
            }
            if len(items) > 40:
                result["_truncated_fields"] = len(items) - 40
            return result
        if isinstance(value, (list, tuple, set)):
            items = list(value)
            max_items = (
                self.MAX_REPRODUCTION_ARGV_ITEMS
                if key.lower() in {"argv", "command_argv"}
                else 20
            )
            result = [
                self.sanitize_problem_value(item, key, depth + 1)
                for item in items[:max_items]
            ]
            if len(items) > max_items:
                result.append({
                    "_truncated_items": len(items) - max_items
                })
            return result
        return self.trim_text(str(value), self.MAX_PROBLEM_TEXT_CHARS)

    def error_signature(self, kind, message, details):
        """Стабильная сигнатура группирует одинаковые сбои без привязки к путям."""
        diagnosis = details.get("diagnosis")
        diagnosis_code = (
            diagnosis.get("code")
            if isinstance(diagnosis, dict)
            else ""
        )
        evidence = (
            details.get("diagnostic_excerpt")
            or details.get("stderr_tail")
            or details.get("exception")
            or message
            or kind
        )
        normalized = str(evidence).lower()
        normalized = re.sub(
            r"(?m)^(?:time|process_pid|thread_name|elapsed_seconds|"
            r"captured_output_bytes|timeout_seconds|returncode)=.*$",
            "<volatile>",
            normalized,
        )
        normalized = re.sub(
            r"threadpoolexecutor-\d+_\d+",
            "threadpoolexecutor-<worker>",
            normalized,
        )
        normalized = re.sub(r"[a-z]:[\\/][^\r\n\"']+", "<path>", normalized)
        normalized = re.sub(r"0x[0-9a-f]+", "<hex>", normalized)
        normalized = re.sub(r"\b\d{2,}\b", "<n>", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()[:2000]
        digest_source = f"{kind}|{diagnosis_code}|{normalized}"
        return hashlib.sha256(
            digest_source.encode("utf-8", errors="replace")
        ).hexdigest()[:16]

    def default_resolution_status(self, kind):
        """Отделяет реальные дефекты программы от ожидаемых пропусков и повторов."""
        if kind in {
            "input_skipped_no_audio",
            "media_file_skipped",
            "folder_skipped_no_media",
        }:
            return "expected_skip"
        if "retry" in kind:
            return "retrying"
        if kind in {"recovery_succeeded", "recovery_failed"}:
            return "recovered" if kind.endswith("succeeded") else "unresolved"
        return "unresolved"

    def write_problem(self, kind, message, **details):
        """Записывает структурированное событие, дедуплицирует повторы и возвращает event_id."""
        severity = str(details.pop("severity", "") or "").lower()
        if severity not in {"info", "warning", "error", "critical"}:
            if kind in {
                "input_skipped_no_audio",
                "folder_skipped_no_media",
            }:
                severity = "info"
            else:
                severity = "warning" if (
                    "retry" in kind
                    or "skipped" in kind
                    or kind.startswith("slow_")
                    or kind.startswith("recovery_")
                ) else "error"

        resolution_status = str(
            details.pop("resolution_status", "")
            or self.default_resolution_status(kind)
        )
        raw_returncode = details.get("returncode")
        if isinstance(raw_returncode, int):
            details["returncode_raw"] = raw_returncode
            details["returncode"] = self.normalize_returncode(raw_returncode)

        guidance = self.problem_guidance(kind)
        supplied_guidance = details.pop("codex", None)
        if isinstance(supplied_guidance, dict):
            guidance.update(supplied_guidance)

        compact_expected_skip = (
            resolution_status == "expected_skip"
            and severity == "info"
        )
        if compact_expected_skip:
            diagnosis = details.get("diagnosis")
            compact_diagnosis = {}
            if isinstance(diagnosis, dict):
                compact_diagnosis = {
                    key: diagnosis.get(key)
                    for key in (
                        "code",
                        "likely_cause",
                        "user_action",
                    )
                    if diagnosis.get(key) not in (None, "")
                }
            compact_details = {
                key: details.get(key)
                for key in (
                    "file",
                    "folder",
                    "output",
                    "returncode",
                    "returncode_raw",
                    "elapsed_seconds",
                    "skip_code",
                )
                if details.get(key) not in (None, "")
            }
            if compact_diagnosis:
                compact_details["diagnosis"] = compact_diagnosis
            compact_details["normalized_outcome"] = "expected_skip"
            details = compact_details

        related_path = (
            details.get("file")
            or details.get("output")
            or details.get("folder")
        )
        if not compact_expected_skip:
            details.setdefault(
                "resources",
                self.resource_snapshot(related_path),
            )
            details.setdefault("execution_context", {
                "app_version": self.APP_VERSION,
                "build_id": getattr(self, "build_id", ""),
                "process_pid": os.getpid(),
                "thread_name": threading.current_thread().name,
                "active_stage": getattr(self, "active_state", {}).get("stage"),
            })
        command_argv = details.pop("command_argv", None)
        if command_argv or details.get("command"):
            details.setdefault("reproduction", {
                "argv": [str(part) for part in command_argv] if command_argv else None,
                "command_text": (
                    self.command_to_text(command_argv)
                    if command_argv
                    else details.get("command")
                ),
                "cwd": os.getcwd(),
                "settings": {
                    "bitrate": getattr(self, "bitrate", None),
                    "max_workers": getattr(self, "max_workers", None),
                    "split_hours": getattr(self, "SPLIT_HOURS", None),
                },
            })

        signature = self.error_signature(kind, message, details)
        clean_details = self.sanitize_problem_value(details)

        with self.log_lock:
            self.problem_counter += 1
            event_id = f"{self.session_id}-{self.problem_counter:05d}"
            self.problem_counts[kind] += 1
            self.problem_severity_counts[severity] += 1
            self.codex_priorities[kind] = {
                "kind": kind,
                "severity": severity,
                **guidance,
            }
            signature_stats = self.problem_signature_stats.setdefault(
                signature,
                {
                    "signature": signature,
                    "kind": kind,
                    "severity": severity,
                    "count": 0,
                    "detailed_count": 0,
                    "suppressed_count": 0,
                    "first_seen": self.now_iso(),
                    "last_seen": self.now_iso(),
                    "sample_event_ids": [],
                    "sample_files": [],
                },
            )
            signature_stats["count"] += 1
            signature_stats["last_seen"] = self.now_iso()
            if len(signature_stats["sample_event_ids"]) < 10:
                signature_stats["sample_event_ids"].append(event_id)
            sample_file = details.get("file")
            if (
                sample_file
                and sample_file not in signature_stats["sample_files"]
                and len(signature_stats["sample_files"]) < 10
            ):
                signature_stats["sample_files"].append(str(sample_file))
            detail_limit = (
                self.MAX_EXPECTED_SKIP_DETAILS_PER_SIGNATURE
                if compact_expected_skip
                else self.MAX_DETAILED_EVENTS_PER_SIGNATURE
            )
            write_detailed = (
                signature_stats["detailed_count"] < detail_limit
            )
            if write_detailed:
                signature_stats["detailed_count"] += 1
            else:
                signature_stats["suppressed_count"] += 1
            self.event_status[event_id] = resolution_status

        record = {
            "schema_version": self.LOG_SCHEMA_VERSION,
            "event_id": event_id,
            "attempt_id": clean_details.get("attempt_id") or event_id,
            "session_id": self.session_id,
            "run_id": getattr(self, "current_run_id", ""),
            "time": self.now_iso(),
            "time_utc": self.utc_now_iso(),
            "severity": severity,
            "kind": kind,
            "resolution_status": resolution_status,
            "error_signature": signature,
            "message": self.trim_text(message, 1000),
            "codex": guidance,
            **clean_details,
        }
        self.event_records[event_id] = record

        if write_detailed:
            line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
            try:
                with self.log_lock:
                    with open(self.problem_log_file, "a", encoding="utf-8") as f:
                        f.write(line)
                        f.flush()
            except Exception as e:
                self.record_diagnostic_failure(
                    "problem_log_write_failed",
                    e,
                    file_path=self.problem_log_file,
                    event_id=event_id,
                    problem_kind=kind,
                )

        try:
            should_log_line = write_detailed or (
                signature_stats["suppressed_count"] in {1, 100, 500, 1000}
            )
            if should_log_line:
                level = {
                    "info": logging.INFO,
                    "warning": logging.WARNING,
                    "error": logging.ERROR,
                    "critical": logging.CRITICAL,
                }.get(severity, logging.ERROR)
                if severity == "critical":
                    level = logging.CRITICAL
                suffix = (
                    ""
                    if write_detailed
                    else f" suppressed={signature_stats['suppressed_count']}"
                )
                self.logger.log(
                    level,
                    "PROBLEM event=%s kind=%s signature=%s%s message=%s",
                    event_id,
                    kind,
                    signature,
                    suffix,
                    self.trim_text(message, 500),
                )
        except Exception:
            pass
        return event_id

    def mark_problem_recovered(self, parent_event_id, action, **details):
        """Связывает исходную проблему с успешным результатом повторной попытки."""
        if parent_event_id:
            self.event_status[parent_event_id] = "recovered"
            if parent_event_id in self.event_records:
                self.event_records[parent_event_id]["resolution_status"] = "recovered"
        return self.write_problem(
            "recovery_succeeded",
            "Повторная попытка успешно устранила исходную проблему.",
            severity="warning",
            resolution_status="recovered",
            parent_event_id=parent_event_id,
            recovery_action=action,
            **details,
        )

    def mark_problem_unresolved(self, parent_event_id, action, **details):
        """Фиксирует неуспешное восстановление с привязкой к исходному событию."""
        if parent_event_id:
            self.event_status[parent_event_id] = "unresolved"
            if parent_event_id in self.event_records:
                self.event_records[parent_event_id]["resolution_status"] = "unresolved"
        return self.write_problem(
            "recovery_failed",
            "Повторная попытка не устранила исходную проблему.",
            severity="error",
            resolution_status="unresolved",
            parent_event_id=parent_event_id,
            recovery_action=action,
            **details,
        )
