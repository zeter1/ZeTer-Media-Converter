"""Synthetic audio regressions; no GUI or production diagnostics initialization."""
import importlib.util
import json
import logging
from pathlib import Path
import subprocess
import tempfile
import unittest
import array
import math
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def owner(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, name)


class Harness(
    owner("videovaudio/audio/folder_workflow.py", "AudioFolderWorkflowMixin"),
    owner("videovaudio/audio/file_conversion.py", "AudioFileConversionMixin"),
    owner("videovaudio/audio/probe.py", "AudioProbeMixin"),
    owner("videovaudio/audio/split.py", "AudioSplitMixin"),
    owner("videovaudio/core/audio_contract.py", "AudioContractMixin"),
    owner("videovaudio/core/paths.py", "PathUtilsMixin"),
):
    cancel_requested = False
    OUTPUT_SAMPLE_RATE_HZ = 44100
    OUTPUT_CHANNELS = 2
    OUTPUT_CHANNEL_LAYOUT = "stereo"
    SAFE_WINDOWS_PATH_LENGTH = 240
    CONCAT_DURATION_TOLERANCE_RATIO = 0.005
    CONCAT_DURATION_TOLERANCE_SECONDS = 5
    CONCAT_DURATION_TOLERANCE_MAX_SECONDS = 15
    SPLIT_HOURS = 10
    MP3_FRAME_SAMPLES = 1152
    SPLIT_BOUNDARY_MARGIN_FRAMES = 2
    SPLIT_MAX_OVERAGE_SECONDS = 0.005
    bitrate = "128k"
    logger = logging.getLogger("audio-test")

    def ffmpeg_base_command(self):
        return ["ffmpeg", "-v", "error"]

    def write_problem(self, *args, **kwargs):
        return "test-event"

    def mark_problem_unresolved(self, *args, **kwargs):
        pass

    def mark_problem_recovered(self, *args, **kwargs):
        pass

    def log_message(self, *args, **kwargs):
        pass

    def set_status(self, *args, **kwargs):
        pass

    def update_progress(self, *args, **kwargs):
        pass

    def command_to_text(self, cmd):
        return str(cmd)

    def trim_text(self, value, limit):
        return value[-limit:]


class AudioRegressions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="audio-regression-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = Harness()
        self.source = self.root / "lesson.mp4"
        self.source.write_bytes(b"source" * 400)
        self.staging = self.root / "stage"
        self.output = self.root / "output"
        self.staging.mkdir()
        self.output.mkdir()

    def conversion(self, duration=10):
        def process(cmd, **kwargs):
            Path(cmd[-1]).write_bytes(b"candidate" * 400)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        self.app.run_process = process
        self.app.get_audio_info = lambda path: {
            "duration_seconds": 10 if Path(path) == self.source else duration,
            "sample_rate_hz": 44100, "channels": 2,
        }
        return self.app.convert_single_file((0, str(self.source), str(self.staging), str(self.output), 0))

    def test_invalid_candidate_preserves_previous_mp3(self):
        previous = self.output / "001_lesson.mp3"
        previous.write_bytes(b"previous-valid-output")
        self.assertFalse(self.conversion(0)["success"])
        self.assertEqual(previous.read_bytes(), b"previous-valid-output")

    def test_short_primary_output_is_rejected(self):
        self.assertFalse(self.conversion(1)["success"])
        self.assertFalse((self.output / "001_lesson.mp3").exists())

    def test_publish_failure_preserves_previous_mp3(self):
        previous = self.output / "001_lesson.mp3"
        previous.write_bytes(b"previous-valid-output")
        with patch("os.replace", side_effect=PermissionError("locked")):
            result = self.conversion()
        self.assertFalse(result["success"])
        self.assertEqual(previous.read_bytes(), b"previous-valid-output")

    def test_successful_conversion(self):
        result = self.conversion()
        self.assertTrue(result["success"])
        self.assertEqual(Path(result["path"]).read_bytes(), b"candidate" * 400)

    def test_probe_falls_back_from_invalid_stream_duration(self):
        for value in ("N/A", "0", "NaN", "inf", "-1"):
            with self.subTest(value=value):
                payload = {"streams": [{"duration": value}], "format": {"duration": "12.5"}}
                self.app.run_process = lambda *a, **k: subprocess.CompletedProcess([], 0, json.dumps(payload), "")
                self.assertEqual(self.app.get_audio_info(str(self.source))["duration_seconds"], 12.5)

    def test_probe_requires_audio_stream(self):
        self.app.run_process = lambda *a, **k: subprocess.CompletedProcess([], 0, '{"streams": [], "format": {"duration": "20"}}', "")
        self.assertEqual(self.app.get_audio_info(str(self.source))["duration_seconds"], 0)

    def test_probe_json_ignores_braces_in_process_header_and_footer(self):
        payload = {"streams": [{"duration": "12"}], "format": {"duration": "12"}}
        log = ('=== PROCESS START ===\nfile=C:/course {part}/lesson.mp4\n'
               'command=ffprobe "C:/course {part}/lesson.mp4"\n\n'
               + json.dumps(payload, indent=4)
               + '\n=== PROCESS END ===\nmessage={finished}\n')
        self.assertEqual(self.app.extract_ffprobe_json(log), payload)

    def test_probe_json_handles_braces_inside_metadata(self):
        payload = {"streams": [], "format": {"tags": {"title": "a } b { c"}}}
        self.assertEqual(self.app.extract_ffprobe_json(json.dumps(payload)), payload)

    def test_real_short_audio_smaller_than_one_kib(self):
        source = self.root / "short.mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=0.02", "-c:a", "libmp3lame",
                        "-b:a", "32k", str(source)],
                       check=True, capture_output=True, timeout=30)
        self.assertLess(source.stat().st_size, 1024)
        self.app.run_process = lambda cmd, **kwargs: subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        self.assertGreater(self.app.get_audio_info(str(source))["duration_seconds"], 0)

    def test_short_garbage_is_still_rejected_by_ffprobe(self):
        source = self.root / "invalid.mp3"
        source.write_bytes(b"This is not an audio stream")
        self.app.run_process = lambda cmd, **kwargs: subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        self.assertEqual(self.app.get_audio_info(str(source))["duration_seconds"], 0)

    def test_real_short_video_conversion_and_split(self):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "color=s=32x32:r=25:d=0.04", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=0.04", "-c:v", "mpeg4",
                        "-c:a", "aac", str(self.source)],
                       check=True, capture_output=True, timeout=30)
        self.app.bitrate = "32k"
        self.app.run_process = lambda cmd, **kwargs: subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        result = self.app.convert_single_file((0, str(self.source), str(self.staging), str(self.output), 0))
        self.assertTrue(result["success"], result)
        self.assertLess(Path(result["path"]).stat().st_size, 1024)
        self.assertTrue(self.app.split_file(result["path"], str(self.output), 0, output_label="short-final"))
        final = self.app.last_split_validation["parts"][0]["file"]
        pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", final,
                              "-f", "s16le", "-ac", "1", "-ar", "8000", "pipe:1"],
                             check=True, capture_output=True, timeout=30).stdout
        self.assertGreater(len(pcm), 0)
        self.assertLess(len(pcm) / 16000, 0.15)

    def test_container_duration_is_not_used_as_selected_track_length(self):
        def process(cmd, **kwargs):
            Path(cmd[-1]).write_bytes(b"candidate" * 400)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        self.app.run_process = process
        self.app.get_audio_info = lambda path: {
            "duration_seconds": 100 if Path(path) == self.source else 10,
            "duration_source": "format" if Path(path) == self.source else "stream",
        }
        result = self.app.convert_single_file((0, str(self.source), str(self.staging), str(self.output), 0))
        self.assertTrue(result["success"])

    def test_failed_duration_fallback_cannot_succeed(self):
        for returncode in (1, -999):
            with self.subTest(returncode=returncode):
                durations = iter((0, 10))
                self.app.get_duration = lambda path: next(durations)
                def process(cmd, **kwargs):
                    Path(cmd[-1]).write_bytes(b"partial" * 400)
                    code = returncode if "duration_fallback" in kwargs["operation"] else 0
                    return subprocess.CompletedProcess(cmd, code, "", "failure")
                self.app.run_process = process
                result = self.app.split_file(str(self.source), str(self.output), 0, known_duration=10)
                self.assertFalse(result)
                self.assertEqual(self.app.last_split_validation["status"], "cancelled" if returncode == -999 else "failed_duration_fallback")

    def test_failed_split_leaves_no_final_candidate(self):
        self.app.get_duration = lambda path: 1
        def process(cmd, **kwargs):
            Path(cmd[-1]).write_bytes(b"partial" * 400)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        self.app.run_process = process
        self.assertFalse(self.app.split_file(str(self.source), str(self.output), 0, known_duration=20))
        self.assertEqual(list(self.output.glob("*.mp3")), [])

    def test_split_rejects_compensating_part_length_errors(self):
        self.app.SPLIT_HOURS = 100 / 3600
        durations = iter((90, 60))
        self.app.get_duration = lambda path: next(durations)
        def process(cmd, **kwargs):
            Path(cmd[-1]).write_bytes(b"candidate" * 400)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        self.app.run_process = process
        self.assertFalse(self.app.split_file(str(self.source), str(self.output), 0, known_duration=150))

    def test_split_never_overwrites_existing_destination(self):
        final = self.output / "course.mp3"
        final.write_bytes(b"previous result")
        self.app.get_duration = lambda path: 10
        def process(cmd, **kwargs):
            Path(cmd[-1]).write_bytes(b"new candidate" * 400)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        self.app.run_process = process
        self.assertFalse(self.app.split_file(str(self.source), str(self.output), 0,
                                            known_duration=10, output_label="course"))
        self.assertEqual(final.read_bytes(), b"previous result")

    def test_split_publication_failure_rolls_back_complete_set(self):
        self.app.SPLIT_HOURS = 100 / 3600
        def process(cmd, **kwargs):
            Path(cmd[-1]).write_bytes(b"candidate" * 400)
            self.app.get_duration = lambda path: float(cmd[cmd.index("-t") + 1])
            return subprocess.CompletedProcess(cmd, 0, "", "")
        self.app.run_process = process
        original_rename = __import__("os").rename
        calls = []
        def rename(source, target):
            calls.append((source, target))
            if len(calls) == 2:
                raise PermissionError("second target locked")
            return original_rename(source, target)
        with patch("os.rename", side_effect=rename):
            result = self.app.split_file(str(self.source), str(self.output), 0, known_duration=150)
        self.assertFalse(result)
        self.assertEqual(self.app.last_split_validation["status"], "failed_publication")
        self.assertEqual(list(self.output.iterdir()), [])

    def test_concat_fallback_recovery_requires_valid_duration(self):
        self.app.event_records = {}
        self.app.session_id = "test_01"
        self.app.max_workers = 1
        self.app.now_iso = lambda: "test-time"
        self.app.update_active_state = lambda *a, **k: None
        self.app.ui_after = lambda *a, **k: None
        self.app.scan_media_files = lambda *a, **k: {"files": [str(self.source)], "status": "ok", "errors": []}
        self.app.convert_single_file = lambda data: {
            "success": True, "index": 0, "path": str(self.source), "duration_seconds": 20,
            "audio_profile": {"sample_rate_hz": 44100, "channels": 2},
        }
        recovered, unresolved = [], []
        self.app.mark_problem_recovered = lambda *a, **k: recovered.append(a)
        self.app.mark_problem_unresolved = lambda *a, **k: unresolved.append(a)
        self.app.get_audio_info = lambda path: {"duration_seconds": 1}
        def process(cmd, **kwargs):
            Path(cmd[-1]).write_bytes(b"partial" * 400)
            return subprocess.CompletedProcess(cmd, 1 if kwargs["operation"] == "concat_full_audio" else 0, "", "")
        self.app.run_process = process
        result = self.app.process_single_folder(str(self.root), 1, 1)
        self.assertEqual(result["status"], "failed_concat_duration_mismatch")
        self.assertEqual(recovered, [])
        self.assertTrue(unresolved)

    def test_previous_outputs_recoverable_and_unrelated_file_untouched(self):
        preserve = owner("videovaudio/audio/folder_workflow.py", "preserve_previous_audio_outputs")
        separate = self.staging / "001_lesson.mp3"
        merged = self.output / "course.mp3"
        unrelated = self.output / "Часть заметки.mp3"
        separate.write_bytes(b"old lesson")
        merged.write_bytes(b"old course")
        unrelated.write_bytes(b"user notes")
        recovery = preserve(str(self.staging), str(self.output), "course.mp3")
        mapping = json.loads((Path(recovery) / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual({Path(src).name: Path(dst).read_bytes() for src, dst in mapping},
                         {"001_lesson.mp3": b"old lesson", "course.mp3": b"old course"})
        self.assertFalse(separate.exists())
        self.assertFalse(merged.exists())
        self.assertEqual(unrelated.read_bytes(), b"user notes")

    def test_backup_failure_preserves_all_originals(self):
        preserve = owner("videovaudio/audio/folder_workflow.py", "preserve_previous_audio_outputs")
        previous = self.staging / "001_lesson.mp3"
        previous.write_bytes(b"original")
        with patch("shutil.copy2", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                preserve(str(self.staging), str(self.output), "course.mp3")
        self.assertEqual(previous.read_bytes(), b"original")

    def test_real_ffmpeg_selected_audio_and_repeat(self):
        # Two distinct tracks: conversion must retain the first (440 Hz),
        # not the louder second (880 Hz). Check decoded samples and frequency.
        subprocess.run(["ffmpeg", "-v", "error", "-y",
                        "-f", "lavfi", "-i", "color=s=32x32:r=10:d=2",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                        "-f", "lavfi", "-i", "sine=frequency=880:duration=2",
                        "-map", "0:v", "-map", "1:a", "-map", "2:a",
                        "-c:v", "mpeg4", "-c:a", "aac", str(self.source)],
                       check=True, capture_output=True, timeout=30)
        original = self.source.read_bytes()
        self.app.run_process = lambda cmd, **kwargs: subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        for _ in range(2):
            result = self.app.convert_single_file((0, str(self.source), str(self.staging), str(self.output), 0))
            self.assertTrue(result["success"], result)
            pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", result["path"],
                                  "-f", "s16le", "-ac", "1", "-ar", "8000", "pipe:1"],
                                 check=True, capture_output=True, timeout=30).stdout
            samples = array.array("h", pcm)
            self.assertLess(abs(len(samples) / 8000 - 2), 0.08)
            middle = samples[2000:10000]
            def energy(hz):
                return abs(sum(value * complex(math.cos(2 * math.pi * hz * i / 8000),
                                                math.sin(2 * math.pi * hz * i / 8000))
                               for i, value in enumerate(middle)))
            self.assertGreater(energy(440), 10 * energy(880))
            self.assertEqual(self.source.read_bytes(), original)

    def test_real_split_preserves_tone_order_across_parts(self):
        source = self.root / "tones.mp3"
        signal = r"aevalsrc=if(lt(t\,1.8)\,sin(2*PI*440*t)\,sin(2*PI*880*t)):s=44100:d=3.5"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", signal,
                        "-ac", "2", "-c:a", "libmp3lame", "-b:a", "128k", str(source)],
                       check=True, capture_output=True, timeout=30)
        self.app.SPLIT_HOURS = 2 / 3600
        self.app.run_process = lambda cmd, **kwargs: subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        self.assertTrue(self.app.split_file(str(source), str(self.output), 0, output_label="tones"))
        parts = self.app.last_split_validation["parts"]
        self.assertEqual(len(parts), 2)
        samples = array.array("h")
        for part in parts:
            self.assertEqual(Path(part["file"]).parent, self.output)
            self.assertLessEqual(part["duration_seconds"], 2.005)
            pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", part["file"],
                                  "-f", "s16le", "-ac", "1", "-ar", "8000", "pipe:1"],
                                 check=True, capture_output=True, timeout=30).stdout
            samples.extend(array.array("h", pcm))
        self.assertLess(abs(len(samples) / 8000 - 3.5), 0.1)
        for start, expected in ((0.3, 440), (1.5, 440), (2.1, 880), (3.1, 880)):
            window = samples[int(start * 8000):int((start + 0.2) * 8000)]
            crossings = sum(a <= 0 < b for a, b in zip(window, window[1:]))
            self.assertLess(abs(crossings / 0.2 - expected), 15)


if __name__ == "__main__":
    unittest.main()
