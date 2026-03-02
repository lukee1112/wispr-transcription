#!/bin/bash
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$INSTALL_DIR/venv"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp}"
PID_FILE="$RUNTIME_DIR/wispr-transcription.pid"

# Check if already running
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Wispr Transcription is already running (PID: $(cat "$PID_FILE"))"
    exit 0
fi

# Ensure display is set (needed for xdotool, X11 key grab, indicator)
if [ -z "${DISPLAY:-}" ]; then
    export DISPLAY=:0
fi

# Activate venv and launch daemon
source "$VENV_DIR/bin/activate"
cd "$INSTALL_DIR"

DISPLAY="$DISPLAY" \
XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}" \
DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}" \
XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" \
PULSE_SERVER="${PULSE_SERVER:-}" \
nohup python3 wispr.py > /dev/null 2>&1 &

echo "Wispr Transcription started (PID: $!)"
