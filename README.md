# Wispr Transcription

Local voice dictation tool for Ubuntu / WSL2. Hold a hotkey to record, release to transcribe and paste.

## Quick Start

```bash
./install.sh   # One-time setup (installs deps, downloads model)
./start.sh     # Start the daemon
./stop.sh      # Stop the daemon
```

## Usage

1. Start the daemon with `./start.sh`
2. Focus any application (VS Code, browser, terminal, etc.)
3. **Hold Right Alt** to start recording — a red "REC" indicator appears
4. **Release Right Alt** to stop and transcribe
5. The transcribed text is pasted into the focused window (via Ctrl+V) and stays on your clipboard

## Changing the Hotkey

Edit `config.py` and change the `HOTKEY` line using X11 keysym names:

```python
HOTKEY = "Alt_R"        # Right Alt (default)
HOTKEY = "Alt_L"        # Left Alt
HOTKEY = "Control_R"    # Right Control
HOTKEY = "Scroll_Lock"  # Scroll Lock
HOTKEY = "F12"          # F12
```

Then restart: `./stop.sh && ./start.sh`

## Configuration

All settings are in `config.py`:

| Setting | Default | Description |
|---|---|---|
| `HOTKEY` | `"Alt_R"` | Hold to record (X11 keysym name) |
| `WHISPER_MODEL` | `"medium"` | Model size: tiny, base, small, medium, large |
| `MIN_RECORDING_SECONDS` | `0.5` | Ignore recordings shorter than this |
| `MAX_RECORDING_SECONDS` | `300` | Truncate recordings longer than this |

## Logs

```bash
tail -f ~/.local/share/wispr-transcription/wispr.log
```

Log files rotate automatically at 5 MB (3 backups kept).

## Troubleshooting

**No audio / microphone not found**
- Check available devices: `pactl list sources short`
- In WSL, ensure PulseAudio/PipeWire is working via WSLg

**Hotkey not working**
- Ensure no other app is grabbing Right Alt
- Check logs for "X11 key grab" messages
- Verify DISPLAY is set: `echo $DISPLAY`
- Try a different hotkey (see above)

**Transcription is slow**
- CPU mode with the medium model takes 10-30s depending on recording length
- Switch to `"small"` or `"base"` model in `config.py` for faster results
- If you have an NVIDIA GPU, install CUDA drivers for much faster transcription

**Text not pasting**
- Text is pasted via Ctrl+V — make sure the focused app supports paste
- The text is always on your clipboard as a fallback
- Verify xdotool works: `xdotool key ctrl+v` (with text on clipboard)

## How It Works

Uses X11 key grabs (`XGrabKey`) for hotkey detection, which works on both native X11 and XWayland (WSLg). Text output uses clipboard + Ctrl+V paste for reliable Unicode support.

## Files

| File | Purpose |
|---|---|
| `wispr.py` | Main daemon (recording, X11 hotkey, text output) |
| `config.py` | All configuration |
| `transcriber.py` | Whisper model + text cleaning |
| `indicator.py` | Red "REC" overlay window |
| `install.sh` | One-time installation |
| `start.sh` / `stop.sh` | Manual start/stop |

## WSL Notes

- Requires WSLg (Windows 11) for audio, display, and input support
- Audio routes through PulseAudio/PipeWire via WSLg
- Keyboard capture uses X11 key grabs (works on WSLg's XWayland)
- Text is pasted via Ctrl+V into WSL GUI apps
