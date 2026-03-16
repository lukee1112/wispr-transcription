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
for mod in "numpy" "sounddevice" "whisper" "torch"; do
    if python3 -c "import $mod" 2>/dev/null; then
        pass "$mod"
    else
        fail "$mod — not importable"
    fi
done
echo ""

# ── 3. System tools ──────────────────────────────────────────
echo "3. System tools"
for tool in ffmpeg; do
    if command -v "$tool" &>/dev/null; then
        pass "$tool"
    else
        fail "$tool — not installed"
    fi
done
echo ""

# ── 4. Windows interop ──────────────────────────────────────
echo "4. Windows interop"
if command -v powershell.exe &>/dev/null; then
    pass "powershell.exe (keyboard hook)"
else
    fail "powershell.exe not found"
fi
if command -v clip.exe &>/dev/null; then
    pass "clip.exe (clipboard)"
else
    fail "clip.exe not found"
fi
if command -v wslpath &>/dev/null; then
    pass "wslpath (path conversion)"
else
    fail "wslpath not found"
fi
echo ""

# ── 5. Display ───────────────────────────────────────────────
echo "5. Display"
if [ -n "${DISPLAY:-}" ]; then
    pass "DISPLAY=$DISPLAY"
else
    warn "DISPLAY not set (indicator overlay may not work)"
fi
echo ""

# ── 6. Audio input ───────────────────────────────────────────
echo "6. Audio input (microphone)"
MIC_RESULT=$(PULSE_SERVER="${PULSE_SERVER:-unix:/mnt/wslg/PulseServer}" python3 -c "
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

# ── 7. Clipboard round-trip ──────────────────────────────────
echo "7. Clipboard (Windows)"
TEST_STR="wispr-smoke-test-$$"
if echo -n "$TEST_STR" | clip.exe 2>/dev/null; then
    pass "clip.exe write OK"
else
    fail "clip.exe write failed"
fi
echo ""

# ── 8. Keyboard hook ─────────────────────────────────────────
echo "8. Keyboard hook"
if [ -f "$INSTALL_DIR/keyhook.exe" ]; then
    pass "keyhook.exe compiled"
else
    fail "keyhook.exe not found — run ./install.sh"
fi
if command -v schtasks.exe &>/dev/null; then
    pass "schtasks.exe (process launcher)"
else
    fail "schtasks.exe not found"
fi
echo ""

# ── 9. Indicator ─────────────────────────────────────────────
echo "9. Recording indicator"
IND_PID=$(python3 "$INSTALL_DIR/indicator.py" &>/dev/null & echo $!)
sleep 1
if kill -0 "$IND_PID" 2>/dev/null; then
    kill "$IND_PID" 2>/dev/null
    wait "$IND_PID" 2>/dev/null
    pass "Indicator launches and terminates"
else
    warn "Indicator process exited (display may not be available)"
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
