"""PyInstaller runtime hook: make the bundled FFmpeg tools discoverable via PATH.

The source-mode application keeps its normal dependency discovery behavior.
No external PATH entry or global environment settings are modified.
"""
import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    bundle = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    ffmpeg = bundle / "ffmpeg.exe"
    ffprobe = bundle / "ffprobe.exe"
    if ffmpeg.is_file() and ffprobe.is_file():
        os.environ["PATH"] = str(bundle) + os.pathsep + os.environ.get("PATH", "")

    # Headless Windows release gate: verify the actual frozen executable,
    # Python imports, and both packaged media processors before publication.
    if sys.argv[1:] == ["--verify-bundle"]:
        import shutil
        import subprocess
        from videovaudio import VideoToAudioConverter

        if VideoToAudioConverter.APP_VERSION != "3.3.5":
            raise SystemExit(21)
        for tool in ("ffmpeg", "ffprobe"):
            executable = shutil.which(tool)
            if not executable or Path(executable).resolve().parent != bundle.resolve():
                raise SystemExit(22)
            check = subprocess.run(
                [executable, "-version"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=30,
                check=False,
            )
            if check.returncode or not check.stdout:
                raise SystemExit(23)
        raise SystemExit(0)
