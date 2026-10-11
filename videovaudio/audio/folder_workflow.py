"""End-to-end workflow for one audio-course folder.

CODEX ROUTE: open this file only when the task matches this responsibility.
Methods are moved whole from the previous owner module; behavior is intentionally unchanged.
"""

import os
import re
import traceback
import subprocess
import time
from collections import Counter
import json
import shutil
import tempfile
import filecmp
from concurrent.futures import ThreadPoolExecutor, as_completed


def preserve_previous_audio_outputs(separate_dir, split_dir, single_output_name):
    """Copy the exact previous-output set to recovery before removing any file."""
    sources = []
    for directory in (separate_dir, split_dir):
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            matched = (
                re.fullmatch(r"\d{3,}_.+\.mp3", name, flags=re.IGNORECASE)
                if directory == separate_dir else
                (re.fullmatch(r"Часть \d+ - .+\.mp3", name, flags=re.IGNORECASE)
                 or os.path.normcase(name) == os.path.normcase(single_output_name))
            )
            if matched and os.path.isfile(path):
                sources.append(path)
    if not sources:
        return None
    # Recovery stays inside an already excluded output directory and outside
    # __temp__, so normal cleanup and recursive media scanning cannot consume it.
    recovery_root = os.path.join(separate_dir, "Предыдущие результаты")
    os.makedirs(recovery_root, exist_ok=True)
    recovery = tempfile.mkdtemp(prefix="run_", dir=recovery_root)
    mapping = [(source, os.path.join(recovery, str(index), os.path.basename(source)))
               for index, source in enumerate(sources)]
    if len({os.path.normcase(target) for _, target in mapping}) != len(mapping):
        raise ValueError("Duplicate recovery targets")
    for source, target in mapping:
        if not os.path.isfile(source) or os.path.lexists(target):
            raise OSError("Recovery mapping changed before copy")
    with open(os.path.join(recovery, "manifest.json"), "x", encoding="utf-8") as stream:
        json.dump(mapping, stream, ensure_ascii=False, indent=2)
    for source, target in mapping:
        os.makedirs(os.path.dirname(target))
        shutil.copy2(source, target)
        if not filecmp.cmp(source, target, shallow=False):
            raise OSError("Recovery copy differs from original")
    # If any copy fails, every original remains. If removal fails, abort the run;
    # all original bytes have already been saved at the recorded destinations.
    for source, target in mapping:
        os.remove(source)
    return recovery


class AudioFolderWorkflowMixin:
    def process_single_folder(self, folder_path, folder_index, total_folders):
        """Обработка одной папки. Успех возвращается только если все этапы реально выполнены."""
        folder_wall_started = time.perf_counter()
        folder_path = self.normalize_folder_path(folder_path)
        folder_name = os.path.basename(folder_path) or folder_path
        initial_event_ids = set(self.event_records)
        summary = {
            "folder": folder_path,
            "folder_name": folder_name,
            "status": "started",
            "outcome": "failed",
            "success": False,
            "input_files": 0,
            "converted_files": 0,
            "failed_files": 0,
            "skipped_files": 0,
            "skipped_file_details": [],
            "problem_event_ids": [],
            "stage_metrics": {},
            "error": "",
            "skip_code": "",
            "skip_reason": "",
            "started_at": self.now_iso(),
        }

        def collect_folder_event_ids():
            summary["problem_event_ids"] = [
                event_id
                for event_id in self.event_records
                if event_id not in initial_event_ids
                and self.event_records[event_id].get("run_id")
                == getattr(self, "current_run_id", "")
            ]

        # CODEX-PHASE F1: initialize folder state, UI and summary.
        self.update_active_state(
            "folder_start",
            status="running",
            folder=folder_path,
            folder_index=folder_index,
            folder_total=total_folders,
            file=None,
        )

        self.ui_after(lambda: self.current_folder_label.config(
            text=f"Текущая папка ({folder_index}/{total_folders}): {folder_name}"
        ))

        self.log_message(f"\n{'='*60}")
        self.log_message(f"📁 ПАПКА {folder_index}/{total_folders}: {folder_name}")
        self.log_message(f"{'='*60}")

        if not os.path.isdir(folder_path):
            msg = f"Папка не существует или недоступна: {folder_path}"
            self.log_message(f"❌ {msg}", level="error")
            event_id = self.write_problem(
                "folder_missing_or_not_directory",
                msg,
                folder=folder_path,
            )
            summary.update({
                "status": "failed_folder_missing",
                "error": msg,
                "finished_at": self.now_iso(),
            })
            summary["problem_event_ids"] = [event_id]
            summary["stage_metrics"]["folder_wall_seconds"] = (
                time.perf_counter() - folder_wall_started
            )
            self.update_active_state(
                "folder_finished",
                folder=folder_path,
                folder_status=summary["status"],
            )
            return summary

        # CODEX-PHASE F2: scan/validate source media before creating outputs.
        self.update_active_state("scan", folder=folder_path)
        scan_started = time.perf_counter()
        scan_result = self.scan_media_files(
            folder_path,
            report_problems=True,
        )
        files = scan_result["files"]
        summary["stage_metrics"]["scan_seconds"] = (
            time.perf_counter() - scan_started
        )
        summary["input_files"] = len(files)
        summary["scan"] = {
            "status": scan_result["status"],
            "error_count": len(scan_result["errors"]),
            "errors": scan_result["errors"][:20],
        }

        if scan_result["errors"]:
            msg = (
                f"Папка '{folder_name}' прочитана не полностью; обработка "
                "остановлена, чтобы не создать аудио с пропущенными файлами"
            )
            self.log_message(f"❌ {msg}", level="error")
            summary.update({
                "status": "failed_scan",
                "error": msg,
                "finished_at": self.now_iso(),
            })
            collect_folder_event_ids()
            summary["stage_metrics"]["folder_wall_seconds"] = (
                time.perf_counter() - folder_wall_started
            )
            self.update_active_state(
                "folder_finished",
                folder=folder_path,
                folder_status=summary["status"],
            )
            return summary

        if not files:
            msg = f"В папке '{folder_name}' нет поддерживаемых видеофайлов"
            self.log_message(f"ℹ️ {msg}")
            event_id = self.write_problem(
                "folder_skipped_no_media",
                msg,
                severity="info",
                resolution_status="expected_skip",
                folder=folder_path,
                skip_code="no_supported_media",
            )
            summary.update({
                "status": "skipped_no_files",
                "outcome": "skipped",
                "skip_code": "no_supported_media",
                "skip_reason": msg,
                "finished_at": self.now_iso(),
            })
            summary["problem_event_ids"] = [event_id]
            summary["stage_metrics"]["folder_wall_seconds"] = (
                time.perf_counter() - folder_wall_started
            )
            self.update_active_state(
                "folder_finished",
                folder=folder_path,
                folder_status=summary["status"],
            )
            return summary

        main_output_path = folder_path
        temp_root = os.path.join(main_output_path, "__temp__")
        short_time = self.session_id.rsplit("_", 1)[-1].replace("-", "")
        temp_name = f"tmp_{folder_index:03d}_{os.getpid()}_{short_time}"
        temp = os.path.join(temp_root, temp_name)

        try:
            # CODEX-PHASE F3: prepare directories and preserve previous outputs.
            os.makedirs(temp, exist_ok=True)

            separate_dir = os.path.join(main_output_path, "Аудио для каждого видео")
            split_dir = os.path.join(main_output_path, "Все видео в аудио по 10 часов")
            os.makedirs(separate_dir, exist_ok=True)
            os.makedirs(split_dir, exist_ok=True)

            single_output_name = os.path.basename(
                self.build_audio_split_output_path(
                    split_dir,
                    folder_name,
                    part_number=1,
                    expected_parts=1,
                )
            )
            recovery = preserve_previous_audio_outputs(separate_dir, split_dir, single_output_name)
            if recovery:
                summary["previous_outputs_backup"] = recovery
                self.log_message(f"📦 Предыдущие MP3 сохранены: {recovery}")

            c_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            self.set_status(f"🚀 Конвертация папки {folder_index}/{total_folders}...")
            self.log_message(f"📁 Результаты сохраняются в: {main_output_path}")
            self.log_message(f"⚡ {self.max_workers} потоков | {len(files)} видеофайлов")
            self.logger.info(
                "FOLDER_INPUT_ORDER_JSON %s",
                json.dumps(
                    {
                        "folder": folder_path,
                        "file_count": len(files),
                        "first_files": files[:5],
                        "last_files": files[-5:] if len(files) > 5 else [],
                        "sort": "natural_sort_key",
                        "note": "Полный список не пишется, чтобы лог не разрастался.",
                    },
                    ensure_ascii=False,
                )
            )

            # CODEX-PHASE F4: parallel per-video conversion and progress collection.
            task_data = [(i, f, temp, separate_dir, c_flags) for i, f in enumerate(files)]
            results_dict = {}
            skipped_results = []

            self.update_active_state(
                "conversion",
                folder=folder_path,
                input_file_count=len(files),
            )
            conversion_wall_started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = [executor.submit(self.convert_single_file, data) for data in task_data]
                completed = 0

                for future in as_completed(futures):
                    result = None
                    try:
                        result = future.result()
                    except Exception as e:
                        self.write_problem(
                            "worker_exception",
                            "Внутренняя ошибка потока конвертации.",
                            exception=f"{type(e).__name__}: {e}",
                            traceback=traceback.format_exc(),
                        )
                        skipped_results.append({
                            "name": "unknown",
                            "reason": str(e),
                            "skip_code": "worker_exception",
                        })

                    if result:
                        if result.get("cancelled"):
                            self.cancel_requested = True
                        elif result.get("success"):
                            idx = result["index"]
                            results_dict[idx] = result
                            name = result.get("name", os.path.basename(result["path"]))
                            elapsed = result.get("elapsed_seconds")
                            suffix = f" ({elapsed:.1f} сек)" if isinstance(elapsed, (int, float)) else ""
                            self.ui_after(lambda n=name, s=suffix: self.log_message(
                                f"   ✓ {n}{s}",
                                persist=False,
                            ))
                        else:
                            skipped_results.append(result)
                            name = result.get("name") or os.path.basename(result.get("file", "unknown"))
                            reason = result.get("reason", "unknown")
                            expected_skip = (
                                result.get("skip_code")
                                == "no_audio_stream"
                            )
                            self.ui_after(lambda n=name, r=reason, expected=expected_skip: self.log_message(
                                (
                                    f"   ℹ️ Без звука, пропущен {n}: {r}"
                                    if expected
                                    else f"   ⚠️ Пропущен {n}: {r}"
                                ),
                                level="info" if expected else "warning",
                            ))

                    completed += 1
                    folder_progress = (completed / len(files)) * 35
                    total_progress = ((folder_index - 1) / total_folders * 100) + (folder_progress / total_folders)
                    self.update_progress(total_progress, f"{int(total_progress)}%")

                    if self.cancel_requested:
                        for f in futures:
                            f.cancel()
                        break
            summary["stage_metrics"]["conversion_wall_seconds"] = (
                time.perf_counter() - conversion_wall_started
            )

            converted_results = [results_dict[i] for i in sorted(results_dict) if i in results_dict]
            converted = [result["path"] for result in converted_results]
            skipped_count = len(files) - len(converted)
            summary["converted_files"] = len(converted)
            summary["failed_files"] = 0
            summary["skipped_files"] = skipped_count
            summary["skipped_no_audio_files"] = sum(
                1
                for item in skipped_results
                if item.get("skip_code") == "no_audio_stream"
            )
            summary["skipped_problem_files"] = max(
                0,
                skipped_count - summary["skipped_no_audio_files"],
            )
            summary["skipped_file_details"] = [
                {
                    "file": item.get("file"),
                    "name": item.get("name"),
                    "reason": item.get("reason"),
                    "skip_code": item.get("skip_code"),
                    "process_log_file": item.get("process_log_file", ""),
                }
                for item in skipped_results[:20]
            ]
            elapsed_items = []
            for result in converted_results:
                elapsed = result.get("elapsed_seconds")
                if not isinstance(elapsed, (int, float)):
                    continue
                duration = float(result.get("duration_seconds", 0) or 0)
                input_size = int(result.get("input_size_bytes", 0) or 0)
                elapsed_items.append({
                    "input_file": result.get("input_file"),
                    "output_file": result.get("path"),
                    "elapsed_seconds": elapsed,
                    "duration_seconds": duration,
                    "input_size_bytes": input_size,
                    "output_size_bytes": result.get("output_size_bytes"),
                    "realtime_factor": duration / elapsed if elapsed > 0 else None,
                    "input_megabytes_per_second": (
                        input_size / (1024 * 1024) / elapsed
                        if elapsed > 0 and input_size > 0
                        else None
                    ),
                })
            conversion_wall = float(
                summary["stage_metrics"].get("conversion_wall_seconds", 0) or 0
            )
            total_converted_duration = sum(
                item["duration_seconds"] for item in elapsed_items
            )
            total_worker_seconds = sum(
                item["elapsed_seconds"] for item in elapsed_items
            )
            total_input_bytes = sum(
                int(item.get("input_size_bytes", 0) or 0)
                for item in elapsed_items
            )
            total_output_bytes = sum(
                int(item.get("output_size_bytes", 0) or 0)
                for item in elapsed_items
            )
            effective_parallelism = (
                total_worker_seconds / conversion_wall
                if conversion_wall > 0
                else None
            )
            summary["conversion_metrics"] = {
                "total_elapsed_worker_seconds": total_worker_seconds,
                "wall_elapsed_seconds": conversion_wall,
                "average_elapsed_seconds": (
                    sum(item["elapsed_seconds"] for item in elapsed_items) / len(elapsed_items)
                    if elapsed_items else 0
                ),
                "total_audio_duration_seconds": total_converted_duration,
                "total_input_bytes": total_input_bytes,
                "total_output_bytes": total_output_bytes,
                "input_megabytes_per_wall_second": (
                    total_input_bytes / (1024 * 1024) / conversion_wall
                    if conversion_wall > 0 and total_input_bytes > 0
                    else None
                ),
                "effective_parallelism": effective_parallelism,
                "worker_pool_utilization_percent": (
                    effective_parallelism / self.max_workers * 100
                    if effective_parallelism is not None
                    and self.max_workers > 0
                    else None
                ),
                "configured_max_workers": self.max_workers,
                "overall_realtime_factor": (
                    total_converted_duration / conversion_wall
                    if conversion_wall > 0
                    else None
                ),
                "slowest_files": sorted(
                    elapsed_items,
                    key=lambda item: item["elapsed_seconds"],
                    reverse=True,
                )[:10],
            }

            # CODEX-PHASE F5: aggregate conversion metrics and validate MP3 profiles/skips.
            profile_counts = Counter()
            profile_mismatches = []
            for result in converted_results:
                profile = result.get("audio_profile")
                profile_key = self.audio_profile_key(profile)
                profile_counts[profile_key] += 1
                if not self.audio_profile_matches_target(profile):
                    profile_mismatches.append({
                        "file": result.get("path"),
                        "profile": profile,
                    })

            summary["audio_profiles"] = {
                "target": self.expected_audio_profile(),
                "by_profile": dict(profile_counts),
                "mismatch_count": len(profile_mismatches),
                "mismatch_files": profile_mismatches[:20],
            }
            if profile_mismatches:
                self.write_problem(
                    "output_audio_profile_mismatch",
                    "Часть созданных MP3 не соответствует единому профилю безопасной склейки.",
                    severity="warning",
                    folder=folder_path,
                    target_profile=self.expected_audio_profile(),
                    mismatch_count=len(profile_mismatches),
                    mismatch_files=profile_mismatches[:20],
                )

            if self.cancel_requested:
                msg = "Папка остановлена по отмене пользователя"
                self.log_message(f"⚠️ {msg}", level="warning")
                summary.update({
                    "status": "cancelled",
                    "outcome": "cancelled",
                    "error": msg,
                })
                return summary

            if not converted:
                msg = "В папке не осталось ни одного видео с пригодной звуковой дорожкой"
                self.log_message(f"❌ {msg}", level="error")
                self.write_problem(
                    "folder_no_usable_audio",
                    msg,
                    folder=folder_path,
                    input_files=len(files),
                    skipped_files=skipped_count,
                    skipped_file_details=summary["skipped_file_details"],
                    codex={
                        "impact": "Итоговое аудио для папки создать невозможно.",
                        "likely_cause": "Все найденные видео без звука, повреждены или недоступны.",
                        "codex_action": "Проверить распределение skip_code и не запускать пустую склейку.",
                    },
                )
                summary.update({"status": "failed_no_usable_audio", "error": msg})
                return summary

            if skipped_count:
                no_audio_count = summary["skipped_no_audio_files"]
                problem_count = summary["skipped_problem_files"]
                if no_audio_count:
                    self.log_message(
                        f"ℹ️ Видео без звука пропущено: {no_audio_count}.",
                        level="info",
                    )
                if problem_count:
                    self.log_message(
                        f"⚠️ Проблемных видео пропущено: {problem_count}.",
                        level="warning",
                    )
                self.log_message(
                    f"🔗 Склейка продолжится из {len(converted)} исправных файлов."
                )

            self.set_status(f"🔗 Склейка аудио папки {folder_index}/{total_folders}...")
            self.log_message("🔗 Склеиваю ВСЕ файлы без повторного перекодирования...")

            # CODEX-PHASE F6: concatenate all valid MP3 files; fallback to transcode if copy fails.
            full_audio = os.path.join(temp, "full_audio.mp3")
            list_file = os.path.join(temp, "concat_list.txt")

            with open(list_file, "w", encoding="utf-8") as L:
                for p in converted:
                    L.write(f"file '{self.escape_concat_path(p)}'\n")

            concat_mode = "copy"
            cmd_concat = [
                *self.ffmpeg_base_command(),
                "-nostdin", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
                "-c:a", "copy",
                "-avoid_negative_ts", "make_zero",
                full_audio
            ]
            self.update_active_state(
                "concat_copy",
                folder=folder_path,
                operation="concat_full_audio",
                output=full_audio,
            )
            concat_copy_started = time.perf_counter()
            concat_result = self.run_process(
                cmd_concat,
                c_flags=c_flags,
                operation="concat_full_audio",
                file_path=list_file
            )
            summary["stage_metrics"]["concat_copy_seconds"] = (
                time.perf_counter() - concat_copy_started
            )

            concat_retry_event_id = None
            if concat_result.returncode not in (0, -999) and not self.cancel_requested:
                concat_retry_event_id = self.write_problem(
                    "ffmpeg_concat_copy_failed_retry_transcode",
                    "Быстрая склейка без перекодирования не сработала. Пробую fallback с перекодированием.",
                    folder=folder_path,
                    list_file=list_file,
                    output=full_audio,
                    command=self.command_to_text(cmd_concat),
                    command_argv=cmd_concat,
                    returncode=concat_result.returncode,
                    elapsed_seconds=getattr(concat_result, "elapsed_seconds", None),
                    process_log_file=getattr(concat_result, "process_log_file", ""),
                    stderr_tail=self.trim_text(concat_result.stderr, 12000),
                )
                try:
                    if os.path.exists(full_audio):
                        os.remove(full_audio)
                except Exception as e:
                    self.write_problem(
                        "concat_partial_output_remove_failed",
                        "Не удалось удалить неполный файл перед fallback-склейкой.",
                        output=full_audio,
                        exception=f"{type(e).__name__}: {e}",
                    )

                concat_mode = "transcode_fallback"
                self.update_active_state(
                    "concat_fallback",
                    folder=folder_path,
                    operation="concat_full_audio_transcode_fallback",
                    parent_event_id=concat_retry_event_id,
                )
                cmd_concat = [
                    *self.ffmpeg_base_command(),
                    "-nostdin", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
                    "-af", f"aresample={self.OUTPUT_SAMPLE_RATE_HZ},asetpts=N/SR/TB",
                    "-ar", str(self.OUTPUT_SAMPLE_RATE_HZ),
                    "-ac", str(self.OUTPUT_CHANNELS),
                    "-c:a", "libmp3lame", "-b:a", self.bitrate,
                    full_audio
                ]
                concat_fallback_started = time.perf_counter()
                concat_result = self.run_process(
                    cmd_concat,
                    c_flags=c_flags,
                    operation="concat_full_audio_transcode_fallback",
                    file_path=list_file
                )
                summary["stage_metrics"]["concat_fallback_seconds"] = (
                    time.perf_counter() - concat_fallback_started
                )
                if concat_result.returncode not in (0, -999):
                    self.mark_problem_unresolved(
                        concat_retry_event_id,
                        "concat_transcode_fallback",
                        folder=folder_path,
                        returncode=concat_result.returncode,
                    )

            if concat_result.returncode == -999 or self.cancel_requested:
                msg = "Склейка остановлена по отмене пользователя"
                self.log_message(f"⚠️ {msg}", level="warning")
                summary.update({
                    "status": "cancelled",
                    "outcome": "cancelled",
                    "error": msg,
                })
                return summary

            if concat_result.returncode != 0:
                msg = f"Ошибка склейки полного файла: ffmpeg returncode={concat_result.returncode}"
                self.log_message(f"❌ {msg}", level="error")
                self.write_problem(
                    "ffmpeg_concat_failed",
                    msg,
                    folder=folder_path,
                    list_file=list_file,
                    output=full_audio,
                    concat_mode=concat_mode,
                    command=self.command_to_text(cmd_concat),
                    command_argv=cmd_concat,
                    returncode=concat_result.returncode,
                    elapsed_seconds=getattr(concat_result, "elapsed_seconds", None),
                    process_log_file=getattr(concat_result, "process_log_file", ""),
                    stderr_tail=self.trim_text(concat_result.stderr, 12000),
                    stdout_tail=self.trim_text(concat_result.stdout, 4000),
                )
                summary.update({"status": "failed_concat", "error": msg})
                return summary

            # CODEX-PHASE F7: verify concat duration and repair timeline mismatch if needed.
            total_original = sum(
                float(result.get("duration_seconds", 0) or 0)
                for result in converted_results
            )
            concat_duration_event_id = None
            concat_manifest_file = ""
            full_audio_info = self.get_audio_info(full_audio)
            full_dur = float(
                full_audio_info.get("duration_seconds", 0) or 0
            )
            self.log_message(f"⏱️  Исходное время: {self.format_duration(total_original)}")
            self.log_message(f"⏱️  Склеенное время: {self.format_duration(full_dur)}")

            mismatch, difference, tolerance = self.duration_mismatch(total_original, full_dur)
            if mismatch and concat_mode == "copy":
                concat_manifest_file = self.save_concat_input_manifest(
                    folder_path,
                    converted_results,
                )
                concat_duration_event_id = self.write_problem(
                    "concat_duration_mismatch_retry_transcode",
                    "Быстрая склейка дала недостоверную длительность. Пересобираю аудио с непрерывной временной шкалой.",
                    severity="warning",
                    folder=folder_path,
                    expected_duration_seconds=total_original,
                    actual_duration_seconds=full_dur,
                    difference_seconds=difference,
                    input_count=len(converted_results),
                    difference_per_input_milliseconds=(
                        difference / len(converted_results) * 1000
                        if converted_results
                        else None
                    ),
                    tolerance_seconds=tolerance,
                    concat_input_manifest=concat_manifest_file,
                    audio_profiles=summary.get("audio_profiles"),
                    concat_process_output=concat_result.stderr,
                    command=self.command_to_text(cmd_concat),
                    command_argv=cmd_concat,
                    codex={
                        "impact": "Быстрый файл не используется; итог будет создан повторно.",
                        "likely_cause": "В concat copy сохранились разрывы DTS/PTS или обнаружен несовместимый профиль MP3.",
                        "codex_action": "Проверить audio_profiles, величину расхождения и повторную длительность.",
                    },
                )
                self.log_message(
                    f"⚠️ Расхождение длительности {self.format_duration(difference)}. "
                    "Повторная точная склейка...",
                    level="warning",
                )
                try:
                    if os.path.exists(full_audio):
                        os.remove(full_audio)
                except Exception as e:
                    self.write_problem(
                        "concat_mismatched_output_remove_failed",
                        "Не удалось удалить MP3 с неверной длительностью перед повторной склейкой.",
                        output=full_audio,
                        exception=f"{type(e).__name__}: {e}",
                    )

                concat_mode = "transcode_duration_repair"
                self.update_active_state(
                    "concat_duration_repair",
                    folder=folder_path,
                    operation="concat_duration_repair",
                    parent_event_id=concat_duration_event_id,
                    concat_input_manifest=concat_manifest_file,
                )
                cmd_concat = [
                    *self.ffmpeg_base_command(),
                    "-nostdin", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
                    "-af", f"aresample={self.OUTPUT_SAMPLE_RATE_HZ},asetpts=N/SR/TB",
                    "-ar", str(self.OUTPUT_SAMPLE_RATE_HZ),
                    "-ac", str(self.OUTPUT_CHANNELS),
                    "-c:a", "libmp3lame", "-b:a", self.bitrate,
                    full_audio,
                ]
                concat_repair_started = time.perf_counter()
                concat_result = self.run_process(
                    cmd_concat,
                    c_flags=c_flags,
                    operation="concat_duration_repair",
                    file_path=list_file,
                )
                summary["stage_metrics"]["concat_duration_repair_seconds"] = (
                    time.perf_counter() - concat_repair_started
                )
                if concat_result.returncode == -999 or self.cancel_requested:
                    msg = "Повторная склейка остановлена по отмене пользователя"
                    summary.update({
                        "status": "cancelled",
                        "outcome": "cancelled",
                        "error": msg,
                    })
                    return summary
                if concat_result.returncode != 0:
                    msg = f"Повторная склейка не удалась: ffmpeg returncode={self.normalize_returncode(concat_result.returncode)}"
                    self.log_message(f"❌ {msg}", level="error")
                    self.mark_problem_unresolved(
                        concat_duration_event_id,
                        "concat_duration_transcode_repair",
                        folder=folder_path,
                        returncode=concat_result.returncode,
                        process_log_file=getattr(
                            concat_result,
                            "process_log_file",
                            "",
                        ),
                    )
                    self.write_problem(
                        "concat_duration_repair_failed",
                        msg,
                        folder=folder_path,
                        command=self.command_to_text(cmd_concat),
                        command_argv=cmd_concat,
                        returncode=concat_result.returncode,
                        elapsed_seconds=getattr(concat_result, "elapsed_seconds", None),
                        process_log_file=getattr(concat_result, "process_log_file", ""),
                        diagnostic_excerpt=concat_result.stderr,
                        parent_event_id=concat_duration_event_id,
                        concat_input_manifest=concat_manifest_file,
                    )
                    summary.update({"status": "failed_concat_repair", "error": msg})
                    return summary

                full_audio_info = self.get_audio_info(full_audio)
                full_dur = float(
                    full_audio_info.get("duration_seconds", 0) or 0
                )
                mismatch, difference, tolerance = self.duration_mismatch(total_original, full_dur)
                self.log_message(
                    f"⏱️  Длительность после исправления: {self.format_duration(full_dur)}"
                )
                if not mismatch:
                    self.mark_problem_recovered(
                        concat_duration_event_id,
                        "concat_duration_transcode_repair",
                        folder=folder_path,
                        actual_duration_seconds=full_dur,
                        difference_seconds=difference,
                        concat_input_manifest=concat_manifest_file,
                    )

            if mismatch:
                msg = (
                    "После точной склейки длительность всё ещё заметно отличается "
                    "от суммы исправных файлов"
                )
                self.log_message(f"❌ {msg}", level="error")
                self.write_problem(
                    "concat_duration_mismatch_after_fallback",
                    msg,
                    folder=folder_path,
                    concat_mode=concat_mode,
                    expected_duration_seconds=total_original,
                    actual_duration_seconds=full_dur,
                    difference_seconds=difference,
                    tolerance_seconds=tolerance,
                    command=self.command_to_text(cmd_concat),
                    command_argv=cmd_concat,
                    diagnostic_excerpt=concat_result.stderr,
                    parent_event_id=concat_duration_event_id,
                    concat_input_manifest=concat_manifest_file,
                )
                if concat_duration_event_id:
                    self.mark_problem_unresolved(
                        concat_duration_event_id,
                        "concat_duration_transcode_repair",
                        folder=folder_path,
                        actual_duration_seconds=full_dur,
                        difference_seconds=difference,
                    )
                if concat_retry_event_id:
                    self.mark_problem_unresolved(
                        concat_retry_event_id, "concat_transcode_fallback",
                        folder=folder_path, reason="duration_mismatch",
                        actual_duration_seconds=full_dur,
                    )
                summary.update({"status": "failed_concat_duration_mismatch", "error": msg})
                return summary

            if not (os.path.exists(full_audio) and os.path.getsize(full_audio) > 0 and full_dur > 0):
                msg = "Склейка завершилась без ошибки, но полный MP3 не создан, слишком маленький или без длительности"
                self.log_message(f"❌ {msg}", level="error")
                self.write_problem(
                    "concat_output_invalid",
                    msg,
                    folder=folder_path,
                    output=full_audio,
                    concat_mode=concat_mode,
                    exists=os.path.exists(full_audio),
                    size=os.path.getsize(full_audio) if os.path.exists(full_audio) else 0,
                    duration=full_dur,
                    command=self.command_to_text(cmd_concat),
                    command_argv=cmd_concat,
                    elapsed_seconds=getattr(concat_result, "elapsed_seconds", None),
                    process_log_file=getattr(concat_result, "process_log_file", ""),
                    stderr_tail=self.trim_text(concat_result.stderr, 12000),
                    stdout_tail=self.trim_text(concat_result.stdout, 4000),
                )
                if concat_retry_event_id:
                    self.mark_problem_unresolved(
                        concat_retry_event_id, "concat_transcode_fallback",
                        folder=folder_path, reason="invalid_output",
                    )
                summary.update({"status": "failed_concat_output_invalid", "error": msg})
                return summary

            if concat_retry_event_id:
                self.mark_problem_recovered(
                    concat_retry_event_id, "concat_transcode_fallback",
                    folder=folder_path, actual_duration_seconds=full_dur,
                    elapsed_seconds=summary["stage_metrics"]["concat_fallback_seconds"],
                )
            summary["concat_validation"] = {
                "mode": concat_mode,
                "expected_duration_seconds": total_original,
                "actual_duration_seconds": full_dur,
                "difference_seconds": difference,
                "input_count": len(converted_results),
                "difference_per_input_milliseconds": (
                    difference / len(converted_results) * 1000
                    if converted_results
                    else None
                ),
                "mp3_frame_duration_milliseconds": (
                    self.MP3_FRAME_SAMPLES
                    / self.OUTPUT_SAMPLE_RATE_HZ
                    * 1000
                ),
                "tolerance_seconds": tolerance,
                "duration_valid": not mismatch,
                "output": self.path_facts(full_audio),
                "audio_profile": {
                    key: full_audio_info.get(key)
                    for key in (
                        "sample_rate_hz",
                        "channels",
                        "channel_layout",
                        "codec_name",
                        "bit_rate",
                    )
                },
                "input_manifest": concat_manifest_file or None,
            }

            # CODEX-PHASE F8: split validated full audio into <=10-hour final parts.
            base_progress = (folder_index - 1) / total_folders * 100 + 35 / total_folders
            self.update_progress(base_progress, f"{int(base_progress)}%")
            self.set_status(f"✂️ Разбивка по 10 часам (папка {folder_index}/{total_folders})...")
            self.update_active_state(
                "split",
                folder=folder_path,
                operation="split_full_audio",
                input=full_audio,
            )
            self.last_split_validation = {}
            split_started = time.perf_counter()
            split_ok = self.split_file(
                full_audio,
                split_dir,
                c_flags,
                folder_index,
                total_folders,
                known_duration=full_dur,
                output_label=folder_name,
            )
            summary["stage_metrics"]["split_seconds"] = (
                time.perf_counter() - split_started
            )
            summary["split_validation"] = dict(
                getattr(self, "last_split_validation", {})
            )

            if self.cancel_requested:
                msg = "Разбивка остановлена по отмене пользователя"
                self.log_message(f"⚠️ {msg}", level="warning")
                summary.update({
                    "status": "cancelled",
                    "outcome": "cancelled",
                    "error": msg,
                })
                return summary

            if not split_ok:
                msg = "Ошибка при разбивке полного аудио на части"
                self.log_message(f"❌ {msg}", level="error")
                summary.update({"status": "failed_split", "error": msg})
                return summary

            summary.update({
                "status": "success_with_skips" if skipped_count else "success",
                "outcome": "success",
                "success": True,
                "finished_at": self.now_iso(),
                "full_duration_seconds": full_dur,
                "original_duration_seconds": total_original,
                "concat_mode": concat_mode,
                "output_dir": main_output_path,
                "output_files": [dict(part) for part in self.last_split_validation['parts']],
            })

            self.log_message(f"✅ Папка '{folder_name}' обработана успешно!")
            self.log_message(f"📍 Результаты сохранены в: {main_output_path}")
            return summary

        except Exception as e:
            msg = f"Ошибка при обработке папки '{folder_name}': {type(e).__name__}: {e}"
            self.log_message(f"💥 {msg}", level="error")
            self.write_problem(
                "folder_unhandled_exception",
                msg,
                folder=folder_path,
                exception=f"{type(e).__name__}: {e}",
                traceback=traceback.format_exc(),
            )
            summary.update({"status": "failed_exception", "error": msg})
            return summary
        # CODEX-PHASE F9: unconditional temp cleanup and final active-state update.
        finally:
            summary.setdefault("finished_at", self.now_iso())
            collect_folder_event_ids()
            cleanup_started = time.perf_counter()
            try:
                if os.path.exists(temp):
                    shutil.rmtree(temp, ignore_errors=True)
                if os.path.isdir(temp_root) and not os.listdir(temp_root):
                    os.rmdir(temp_root)
            except Exception as e:
                self.write_problem(
                    "temp_cleanup_failed",
                    "Не удалось удалить временную папку.",
                    folder=folder_path,
                    temp_dir=temp,
                    temp_root=temp_root,
                    exception=f"{type(e).__name__}: {e}",
                )
            summary["stage_metrics"]["cleanup_seconds"] = (
                time.perf_counter() - cleanup_started
            )
            summary["stage_metrics"]["folder_wall_seconds"] = (
                time.perf_counter() - folder_wall_started
            )
            self.update_active_state(
                "folder_finished",
                folder=folder_path,
                folder_status=summary.get("status"),
                folder_elapsed_seconds=summary["stage_metrics"][
                    "folder_wall_seconds"
                ],
            )
