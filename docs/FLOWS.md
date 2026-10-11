# ZeTer Media Converter — последовательности обработки

## Audio: queue -> folder -> MP3
```text
UI start
  -> run/audio.py::start
  -> run/audio.py::process_queue
  -> audio/folder_workflow.py::process_single_folder
       F1 state/UI summary
       F2 scan
       F3 output/temp prep
       F4 parallel audio/file_conversion.py::convert_single_file
       F5 metrics/profile/skips
       F6 concat full MP3
       F7 duration validation/repair
       F8 audio/split.py::split_file
       F9 cleanup
  -> run/lifecycle.py::done
```

## Audio: one file
```text
audio/file_conversion.py::convert_single_file
  A1 build command
  A2 run_process
  A3 classify + optional LAME fallback
  A4 validate/publish separate MP3
  A5 terminal invalid-output path
```

## Audio split
```text
audio/split.py::split_file
  S1 duration contract
  S2 each part: copy-first -> transcode fallback
  S3 at least one part
  S4 total duration validation
  S5 success validation summary
```

## Video: queue -> course parts
```text
UI start_video_merge
  -> run/video.py::start_video_merge
  -> run/video.py::process_video_queue
  -> video/folder_workflow.py::process_video_folder
       V1 scan
       V2 probe inputs
       V3 choose target + groups
       V4 video/operations.py creates validated staged groups
       V5 atomic publish
       V6 cleanup
  -> run/lifecycle.py::done
```

## Subprocess lifecycle
```text
feature builds argv
  -> process_runner.py::run_process
       P1 finalizer definition
       P2 Popen + live context
       P3 poll exit/cancel/timeout/fatal LAME assertion
       P4 footer + diagnostics + CompletedProcess
```

## Diagnostics
```text
feature/problem
  -> diagnostics/events.py::write_problem
  -> diagnostics/lifecycle.py::update_active_state (live state)
  -> diagnostics/run_reports.py::save_run_summary
       -> codex_report.py
       -> integrity.py
       -> health.py
  -> storage/atomic.py for important JSON/text writes
```
