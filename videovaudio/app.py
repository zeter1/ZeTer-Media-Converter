"""Application composition root.

The public VideoToAudioConverter class is assembled from responsibility-focused mixins.
Keep app-wide constants and initialization here; put feature logic in its owner module.
"""

import os
import re
from tkinter import messagebox
import threading
import time
from collections import Counter
from shutil import which

from .ui import UIMixin
from .queues import QueueMixin
from .core import CoreMixin
from .diagnostics import DiagnosticsMixin
from .process_runner import ProcessRunnerMixin
from .audio import AudioMixin
from .video import VideoMixin
from .run import RunMixin
from .storage import StorageMixin

class VideoToAudioConverter(
    UIMixin,
    QueueMixin,
    CoreMixin,
    DiagnosticsMixin,
    ProcessRunnerMixin,
    AudioMixin,
    VideoMixin,
    RunMixin,
    StorageMixin,
):
    APP_NAME = "ZeTer Media Converter"
    APP_VERSION = "3.3.5"
    LOG_SCHEMA_VERSION = 5
    PROBLEM_LOG_RETENTION_DAYS = 120
    MAX_PROCESS_LOG_BYTES = 64 * 1024
    MAX_PROBLEM_TEXT_CHARS = 3500
    MAX_DETAILED_EVENTS_PER_SIGNATURE = 20
    MAX_EXPECTED_SKIP_DETAILS_PER_SIGNATURE = 1
    MAX_REPRODUCTION_ARGV_ITEMS = 160
    HEARTBEAT_INTERVAL_SECONDS = 30
    ATOMIC_REPLACE_MAX_ATTEMPTS = 4
    ATOMIC_REPLACE_RETRY_DELAY_SECONDS = 0.05
    DIAGNOSTIC_FAILURE_LOG_SAMPLES = frozenset({1, 5, 20, 100})
    STALE_ATOMIC_TEMP_MIN_AGE_SECONDS = 60
    COMPRESS_DETAILED_LOGS_AFTER_DAYS = 7
    SAFE_WINDOWS_PATH_LENGTH = 240
    OUTPUT_SAMPLE_RATE_HZ = 44100
    OUTPUT_CHANNELS = 2
    OUTPUT_CHANNEL_LAYOUT = "stereo"
    MP3_FRAME_SAMPLES = 1152
    SPLIT_BOUNDARY_MARGIN_FRAMES = 2
    SPLIT_MAX_OVERAGE_SECONDS = 0.005
    CONCAT_DURATION_TOLERANCE_RATIO = 0.005
    CONCAT_DURATION_TOLERANCE_SECONDS = 5.0
    CONCAT_DURATION_TOLERANCE_MAX_SECONDS = 15.0
    VIDEO_OUTPUT_FOLDER = "Объединение всех видео по 10 часов"
    VIDEO_TEMP_FOLDER = "__temp_video_merge__"
    VIDEO_OUTPUT_PATTERN = re.compile(
        r"^Часть \d{3,}\.mp4$",
        flags=re.IGNORECASE,
    )
    VIDEO_MAX_DURATION_OVERAGE_SECONDS = 1.0
    VIDEO_NORMALIZE_PRESET = "veryfast"
    VIDEO_BITRATE_CHOICES = ("1500k", "2500k", "4000k", "6000k", "8000k")
    VIDEO_AUDIO_BITRATE_CHOICES = ("96k", "128k", "160k", "192k", "256k", "320k")
    VIDEO_RESOLUTIONS = {
        "720p": (1280, 720),
        "1080p": (1920, 1080),
    }
    DEFAULT_VIDEO_BITRATE = "2500k"
    DEFAULT_VIDEO_AUDIO_BITRATE = "160k"
    DEFAULT_VIDEO_RESOLUTION = "720p"
    VIDEO_AUDIO_SAMPLE_RATE_HZ = 48000
    VIDEO_AUDIO_CHANNELS = 2
    WINDOWS_CHILD_ERROR_MODE_FLAGS = 0x0002
    windows_error_mode_lock = threading.Lock()
    windows_error_mode_configured = False

    def __init__(self, root):
        self.root = root
        self.root.title(self.APP_NAME)
        self.root.geometry("1050x800")

        self.SPLIT_HOURS = 10.0
        self.bitrate = "128k"
        self.max_workers = min(os.cpu_count() or 1, 4)

        self.is_running = False
        self.cancel_requested = False
        self.active_processes = set()
        self.process_lock = threading.Lock()
        self.log_lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.active_state_write_lock = threading.Lock()
        self.diagnostic_failure_lock = threading.Lock()
        self.last_run_summary = {}
        self.problem_counter = 0
        self.problem_counts = Counter()
        self.problem_severity_counts = Counter()
        self.codex_priorities = {}
        self.problem_signature_stats = {}
        self.event_records = {}
        self.event_status = {}
        self.process_contexts = {}
        self.diagnostic_failures = {}
        self.diagnostic_retry_counts = Counter()
        self.active_state = {}
        self.heartbeat_stop_event = threading.Event()
        self.heartbeat_thread = None
        self.session_started_monotonic = time.monotonic()
        self.crash_log_handle = None
        self.crash_log_initial_size = 0
        self.resource_metrics_lock = threading.Lock()
        self.run_resource_metrics = {}
        self.previous_cpu_times = None

        # Очередь папок для конвертации (всегда пустая при запуске)
        self.folder_queue = []
        self.video_folder_queue = []
        self.active_job_kind = None
        self.active_video_settings = {
            "resolution": self.DEFAULT_VIDEO_RESOLUTION,
            "video_bitrate": self.DEFAULT_VIDEO_BITRATE,
            "audio_bitrate": self.DEFAULT_VIDEO_AUDIO_BITRATE,
            "force_encode": True,
        }

        self.setup_logging()
        self.install_exception_hooks()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.create_interface()

        missing_tools = [tool for tool in ("ffmpeg", "ffprobe") if not which(tool)]
        if missing_tools:
            msg = "Не найдены зависимости: " + ", ".join(missing_tools)
            self.write_problem(
                "missing_dependency",
                msg,
                missing_tools=missing_tools,
                PATH=os.environ.get("PATH", ""),
            )
            messagebox.showwarning("Ошибка зависимости", msg)
