# Wispr Transcription

Local voice dictation tool for WSL2 / Ubuntu. Hold a hotkey to record, release to transcribe and paste.

## Quick Start

```bash
./install.sh   # One-time setup (installs deps, downloads model)
./start.sh     # Start the daemon
./stop.sh      # Stop the daemon
```

## Usage

1. Start the daemon with `./start.sh`
2. Focus any window (browser, VS Code, terminal, etc.)
3. **Hold Right Alt** to start recording — a red "REC" indicator appears
4. **Release Right Alt** to stop and transcribe
5. The transcribed text is pasted into the focused window and stays on your clipboard

Works in **all windows** — Windows apps (Chrome, Gmail, Slack) and WSL apps alike.

## Changing the Hotkey

Edit `config.py` and change the `HOTKEY` line:

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
| `HOTKEY` | `"Alt_R"` | Hold to record |
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
- Check `PULSE_SERVER` is set: `echo $PULSE_SERVER`
- Should be `unix:/mnt/wslg/PulseServer` on WSL2
- Install ALSA PulseAudio plugin: `sudo apt install libasound2-plugins`

**Hotkey not working**
- Check logs for "keyboard hook" messages
- Verify PowerShell works: `powershell.exe -Command "echo test"`
- Try a different hotkey (see above)

**Transcription is slow**
- CPU mode with the medium model takes 10-30s depending on recording length
- Switch to `"small"` or `"base"` model in `config.py` for faster results
- If you have an NVIDIA GPU, install CUDA drivers for much faster transcription

**Text not pasting**
- Text is pasted via Ctrl+V using Windows clipboard
- The text is always on your clipboard as a fallback

## How It Works

Keyboard capture uses a Windows-side PowerShell script with Win32 `SetWindowsHookEx` — this is the only method that works globally on WSL2/WSLg across all windows (Windows native and WSL GUI apps). Audio recording uses PulseAudio through WSLg. Transcription runs locally via OpenAI Whisper. Text output uses `clip.exe` + PowerShell `SendKeys` for paste.

## Files

| File | Purpose |
|---|---|
| `wispr.py` | Main daemon (recording, text output) |
| `keyhook.ps1` | Windows keyboard hook (PowerShell + C#) |
| `config.py` | All configuration |
| `transcriber.py` | Whisper model + text cleaning |
| `indicator.py` | Red "REC" overlay window |
| `install.sh` | One-time installation |
| `smoke_test.sh` | Post-install verification |
| `start.sh` / `stop.sh` | Manual start/stop |

## WSL Notes

- Requires WSLg (Windows 11) for audio and display support
- Audio routes through PulseAudio/PipeWire via WSLg
- Keyboard capture runs on the Windows side (PowerShell + Win32 hook)
- Text paste uses Windows clipboard + SendKeys (works in all apps)
