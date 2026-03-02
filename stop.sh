#!/bin/bash
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp}"
PID_FILE="$RUNTIME_DIR/wispr-transcription.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        rm -f "$PID_FILE"
        echo "Wispr Transcription stopped (PID: $PID)"
    else
        echo "Wispr Transcription is not running (stale PID file)"
        rm -f "$PID_FILE"
    fi
else
    # Try to find it by matching the exact command
    PIDS=$(pgrep -xf "python3 wispr.py" 2>/dev/null || true)
    if [ -n "$PIDS" ]; then
        echo "$PIDS" | xargs kill 2>/dev/null
        echo "Wispr Transcription stopped"
    else
        echo "Wispr Transcription is not running"
    fi
fi
