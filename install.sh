#!/bin/bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$INSTALL_DIR/venv"
AUTOSTART_DIR="$HOME/.config/autostart"
DATA_DIR="$HOME/.local/share/wispr-transcription"

echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Wispr Transcription — Installer            ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""

# ── Detect environment ─────────────────────────────────────────
if grep -qi microsoft /proc/version 2>/dev/null; then
    IS_WSL=true
    echo -e "${BLUE}Environment:${NC} WSL"
else
    IS_WSL=false
    echo -e "${BLUE}Environment:${NC} Native Ubuntu"
fi

if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
    HAS_GPU=true
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
    echo -e "${BLUE}GPU:${NC}         $GPU_NAME (CUDA will be used)"
else
    HAS_GPU=false
    echo -e "${BLUE}GPU:${NC}         None detected — CPU will be used"
fi
echo ""

# ── System dependencies ───────────────────────────────────────
echo -e "${YELLOW}[1/5]${NC} Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-pip python3-venv python3-dev python3-tk \
    portaudio19-dev \
    ffmpeg \
    xdotool \
    xclip \
    libnotify-bin \
    > /dev/null
echo -e "  ${GREEN}done${NC}"

# ── Python virtual environment ─────────────────────────────────
echo -e "${YELLOW}[2/5]${NC} Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q
echo -e "  ${GREEN}done${NC}"

# ── Python packages ────────────────────────────────────────────
echo -e "${YELLOW}[3/5]${NC} Installing Python dependencies..."
pip install -q -r "$INSTALL_DIR/requirements.txt"
echo -e "  ${GREEN}done${NC}"

# ── Download Whisper model ─────────────────────────────────────
echo -e "${YELLOW}[4/5]${NC} Downloading Whisper medium model (~1.5 GB)..."
python3 -c "import whisper; whisper.load_model('medium')"
echo -e "  ${GREEN}done${NC}"

# ── Autostart & scripts ───────────────────────────────────────
echo -e "${YELLOW}[5/5]${NC} Setting up autostart and scripts..."
chmod +x "$INSTALL_DIR/start.sh" "$INSTALL_DIR/stop.sh" "$INSTALL_DIR/wispr.py"
mkdir -p "$DATA_DIR" "$AUTOSTART_DIR"

cat > "$AUTOSTART_DIR/wispr-transcription.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Wispr Transcription
Comment=Local voice dictation tool
Exec=$INSTALL_DIR/start.sh
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
StartupNotify=false
Terminal=false
EOF

echo -e "  ${GREEN}done${NC}"

# ── Verify X11 key grab ──────────────────────────────────────
echo ""
echo -e "${YELLOW}Verifying keyboard capture...${NC}"
if python3 -c "
from Xlib import display, X, XK
d = display.Display()
root = d.screen().root
keycode = d.keysym_to_keycode(XK.XK_Alt_R)
root.grab_key(keycode, X.AnyModifier, True, X.GrabModeAsync, X.GrabModeAsync)
d.sync()
root.ungrab_key(keycode, X.AnyModifier)
d.sync()
d.close()
" 2>/dev/null; then
    echo -e "  ${GREEN}X11 key grab works!${NC}"
else
    echo -e "  ${RED}WARNING: X11 key grab failed.${NC}"
    echo "  Make sure DISPLAY is set and an X server is running."
    if [ "$IS_WSL" = true ]; then
        echo "  WSL requires WSLg (Windows 11) for X11 support."
    fi
fi

# ── Summary ────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Installation complete!                     ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo "  Start:   ./start.sh"
echo "  Stop:    ./stop.sh"
echo "  Hotkey:  Hold Right Alt to record, release to transcribe"
echo "  Logs:    ~/.local/share/wispr-transcription/wispr.log"
echo ""
if [ "$IS_WSL" = true ]; then
    echo -e "${YELLOW}WSL note:${NC} Requires WSLg (Windows 11) for audio & display support."
    echo "  Test audio: paplay /usr/share/sounds/freedesktop/stereo/bell.oga"
    echo ""
fi
