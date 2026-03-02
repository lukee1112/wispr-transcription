"""Configuration for Wispr Transcription."""
import os
from pathlib import Path

# Hotkey - hold to record, release to transcribe
# Use X11 keysym names. Common options:
#   "Alt_R"        Right Alt (default)
#   "Alt_L"        Left Alt
#   "Control_R"    Right Control
#   "Scroll_Lock"  Scroll Lock
#   "F12"          F12
HOTKEY = "Alt_R"

# Whisper settings
WHISPER_MODEL = "medium"
WHISPER_LANGUAGE = "en"

# Audio settings
SAMPLE_RATE = 16000  # 16kHz mono, optimal for Whisper
CHANNELS = 1
MIN_RECORDING_SECONDS = 0.5
MAX_RECORDING_SECONDS = 300  # 5 minutes

# Output settings
TYPING_DELAY_MS = 8  # ms between keystrokes for xdotool (fallback only)

# Filler words - always removed
FILLER_WORDS = [
    "uh huh", "mm hmm", "mm-hmm", "um", "uh", "er", "ah",
    "hmm", "hm",
]

# Context-dependent fillers - removed only in filler positions
CONTEXT_FILLERS = [
    "you know", "i mean", "so yeah", "like", "basically", "actually",
]

# Paths
DATA_DIR = Path.home() / ".local" / "share" / "wispr-transcription"
LOG_FILE = DATA_DIR / "wispr.log"
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
PID_FILE = RUNTIME_DIR / "wispr-transcription.pid"
INSTALL_DIR = Path(__file__).parent.resolve()
