"""Configuration for Wispr Transcription."""
import os
from pathlib import Path

# Load .env file if present
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), value)

# Hotkey - hold to record, release to transcribe
# Use key names from the list below.
#   "Alt_R"        Right Alt (default)
#   "Alt_L"        Left Alt
#   "Control_R"    Right Control
#   "Control_L"    Left Control
#   "Scroll_Lock"  Scroll Lock
#   "F12"          F12
#   "F11"          F11
#   "F10"          F10
HOTKEY = "Alt_R"

# Windows virtual key codes (used by keyhook.ps1)
VK_CODES = {
    "Alt_R": 0xA5,
    "Alt_L": 0xA4,
    "Control_R": 0xA3,
    "Control_L": 0xA2,
    "Scroll_Lock": 0x91,
    "F12": 0x7B,
    "F11": 0x7A,
    "F10": 0x79,
}

# OpenAI API
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Whisper settings
WHISPER_LANGUAGE = "en"

# Audio settings
SAMPLE_RATE = 16000  # 16kHz mono, optimal for Whisper
CHANNELS = 1
MIN_RECORDING_SECONDS = 0.5
MAX_RECORDING_SECONDS = 300  # 5 minutes
SILENCE_RMS_THRESHOLD = 0.001  # Below this RMS, audio is treated as silence

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
