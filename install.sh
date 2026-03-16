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
echo -e "${YELLOW}[1/6]${NC} Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-pip python3-venv python3-dev python3-tk \
    portaudio19-dev libasound2-plugins \
    ffmpeg \
    xdotool \
    xclip \
    libnotify-bin \
    > /dev/null
echo -e "  ${GREEN}done${NC}"

# ── Python virtual environment ─────────────────────────────────
echo -e "${YELLOW}[2/6]${NC} Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q
echo -e "  ${GREEN}done${NC}"

# ── Python packages ────────────────────────────────────────────
echo -e "${YELLOW}[3/6]${NC} Installing Python dependencies..."
pip install -q -r "$INSTALL_DIR/requirements.txt"
echo -e "  ${GREEN}done${NC}"

# ── Download Whisper model ─────────────────────────────────────
echo -e "${YELLOW}[4/6]${NC} Downloading Whisper medium model (~1.5 GB)..."
python3 -c "import whisper; whisper.load_model('medium')"
echo -e "  ${GREEN}done${NC}"

# ── Compile keyboard hook ─────────────────────────────────────
echo -e "${YELLOW}[5/6]${NC} Compiling keyboard hook..."
WIN_CS=$(wslpath -w "$INSTALL_DIR/keyhook.cs" 2>/dev/null)
WIN_EXE=$(wslpath -w "$INSTALL_DIR/keyhook.exe" 2>/dev/null)
if [ -n "$WIN_CS" ]; then
    if powershell.exe -NoProfile -Command \
        "& 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe' /nologo /target:exe /reference:System.Windows.Forms.dll '/out:$WIN_EXE' '$WIN_CS'" 2>/dev/null; then
        echo -e "  ${GREEN}done${NC}"
    else
        echo -e "  ${RED}FAILED: Could not compile keyhook.cs${NC}"
        echo "  Keyboard capture will not work without this."
    fi
else
    echo -e "  ${RED}FAILED: wslpath not available${NC}"
fi

# ── Autostart & scripts ───────────────────────────────────────
echo -e "${YELLOW}[6/6]${NC} Setting up autostart and scripts..."
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

# ── Verify keyboard hook ─────────────────────────────────────
echo ""
echo -e "${YELLOW}Verifying keyboard capture...${NC}"
if [ -f "$INSTALL_DIR/keyhook.exe" ]; then
    echo -e "  ${GREEN}keyhook.exe compiled successfully${NC}"
else
    echo -e "  ${RED}WARNING: keyhook.exe not found.${NC}"
    echo "  Keyboard capture will not work. Check .NET Framework installation."
fi
if command -v schtasks.exe &>/dev/null; then
    echo -e "  ${GREEN}schtasks.exe available (process launcher)${NC}"
else
    echo -e "  ${RED}WARNING: schtasks.exe not found.${NC}"
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
