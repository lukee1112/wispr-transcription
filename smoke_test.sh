#!/bin/bash
# Post-install smoke test — run after ./install.sh to verify everything works.
# Usage: ./smoke_test.sh

set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$INSTALL_DIR/venv"
PASS=0
FAIL=0
WARN=0

pass() { echo -e "  ${GREEN}PASS${NC}  $1"; ((PASS++)); }
fail() { echo -e "  ${RED}FAIL${NC}  $1"; ((FAIL++)); }
warn() { echo -e "  ${YELLOW}WARN${NC}  $1"; ((WARN++)); }

echo ""
echo "Wispr Transcription — Smoke Test"
echo "================================"
echo ""

# ── 1. Virtual environment ────────────────────────────────────
echo "1. Virtual environment"
if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
    pass "venv exists and activated"
else
    fail "venv not found at $VENV_DIR — run ./install.sh first"
    echo ""
    echo -e "${RED}Cannot continue without venv. Run ./install.sh first.${NC}"
    exit 1
fi
echo ""

# ── 2. Python dependencies ───────────────────────────────────
echo "2. Python imports"
for mod in "numpy" "sounddevice" "whisper" "torch" "Xlib"; do
    if python3 -c "import $mod" 2>/dev/null; then
        pass "$mod"
    else
        fail "$mod — not importable"
    fi
done
echo ""

# ── 3. System tools ──────────────────────────────────────────
echo "3. System tools"
for tool in xdotool xclip notify-send ffmpeg; do
    if command -v "$tool" &>/dev/null; then
        pass "$tool"
    else
        fail "$tool — not installed"
    fi
done
echo ""

# ── 4. Display ───────────────────────────────────────────────
echo "4. Display"
if [ -n "${DISPLAY:-}" ]; then
    pass "DISPLAY=$DISPLAY"
else
    fail "DISPLAY not set"
fi
echo ""

# ── 5. Audio input ───────────────────────────────────────────
echo "5. Audio input (microphone)"
MIC_RESULT=$(python3 -c "
import sounddevice as sd
try:
    dev = sd.query_devices(kind='input')
    print('OK:' + dev['name'])
except Exception as e:
    print('FAIL:' + str(e))
" 2>&1)
if [[ "$MIC_RESULT" == OK:* ]]; then
    pass "Microphone: ${MIC_RESULT#OK:}"
else
    fail "No microphone: ${MIC_RESULT#FAIL:}"
fi
echo ""

# ── 6. X11 key grab ──────────────────────────────────────────
echo "6. X11 key grab (hotkey capture)"
GRAB_RESULT=$(python3 -c "
from Xlib import display, X, XK
try:
    d = display.Display()
    root = d.screen().root
    keycode = d.keysym_to_keycode(XK.XK_Alt_R)
    root.grab_key(keycode, X.AnyModifier, True, X.GrabModeAsync, X.GrabModeAsync)
    d.sync()
    root.ungrab_key(keycode, X.AnyModifier)
    d.sync()
    d.close()
    print('OK')
except Exception as e:
    print('FAIL:' + str(e))
" 2>&1)
if [ "$GRAB_RESULT" = "OK" ]; then
    pass "XGrabKey works on this display"
else
    fail "XGrabKey failed: ${GRAB_RESULT#FAIL:}"
fi
echo ""

# ── 7. Clipboard ─────────────────────────────────────────────
echo "7. Clipboard"
TEST_STR="wispr-smoke-test-$$"
if echo -n "$TEST_STR" | xclip -selection clipboard 2>/dev/null; then
    CLIP=$(xclip -selection clipboard -o 2>/dev/null)
    if [ "$CLIP" = "$TEST_STR" ]; then
        pass "Clipboard round-trip OK"
    else
        fail "Clipboard wrote but read back wrong value"
    fi
else
    fail "Could not write to clipboard"
fi
echo ""

# ── 8. xdotool ──────────────────────────────────────────────
echo "8. xdotool"
if xdotool getactivewindow &>/dev/null; then
    pass "xdotool can detect active window"
else
    warn "xdotool getactivewindow failed (may work differently on WSLg)"
fi
echo ""

# ── 9. Indicator ─────────────────────────────────────────────
echo "9. Recording indicator"
IND_PID=$(python3 "$INSTALL_DIR/indicator.py" &>/dev/null & echo $!)
sleep 0.5
if kill -0 "$IND_PID" 2>/dev/null; then
    kill "$IND_PID" 2>/dev/null
    wait "$IND_PID" 2>/dev/null
    pass "Indicator launches and terminates"
else
    fail "Indicator process died immediately"
fi
echo ""

# ── 10. Whisper model ────────────────────────────────────────
echo "10. Whisper model"
MODEL_RESULT=$(python3 -c "
import whisper, os
model_path = os.path.expanduser('~/.cache/whisper/medium.pt')
if os.path.exists(model_path):
    print('OK')
else:
    print('MISSING')
" 2>&1)
if [ "$MODEL_RESULT" = "OK" ]; then
    pass "Whisper medium model cached at ~/.cache/whisper/"
else
    warn "Model not cached yet (will download on first start)"
fi
echo ""

# ── 11. Notify ───────────────────────────────────────────────
echo "11. Desktop notifications"
if notify-send "Wispr Smoke Test" "If you see this, notifications work!" --urgency low 2>/dev/null; then
    pass "notify-send works (you should see a notification)"
else
    warn "notify-send failed (notifications are optional)"
fi
echo ""

# ── Summary ──────────────────────────────────────────────────
echo "================================"
echo -e "Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}, ${YELLOW}${WARN} warnings${NC}"
echo ""
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}All checks passed! Ready to run ./start.sh${NC}"
else
    echo -e "${RED}Some checks failed. Fix the issues above before starting.${NC}"
fi
echo ""
