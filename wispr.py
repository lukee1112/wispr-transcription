#!/usr/bin/env python3
"""Wispr Transcription - Local voice dictation daemon.

Hold a hotkey to record, release to transcribe and paste into the focused window.
Uses a Windows-side keyboard hook (PowerShell) for key capture on WSL2.
"""
import os
import sys
import shutil
import signal
import socket
import subprocess
import threading
import time
import logging
import atexit
from logging.handlers import RotatingFileHandler

from pathlib import Path

import numpy as np
import sounddevice as sd

from config import (
    HOTKEY, VK_CODES, SAMPLE_RATE, CHANNELS,
    MIN_RECORDING_SECONDS, MAX_RECORDING_SECONDS,
    SILENCE_RMS_THRESHOLD,
    DATA_DIR, LOG_FILE, PID_FILE, INSTALL_DIR,
    OPENAI_API_KEY,
)
from transcriber import Transcriber

logger = logging.getLogger("wispr")


class WisprDaemon:
    def __init__(self):
        self.transcriber = Transcriber()
        self.recording = False
        self.processing = False
        self.audio_frames = []
        self.stream = None
        self.indicator_proc = None
        self.lock = threading.Lock()
        self._hook_lock = threading.Lock()  # serialises writes to _hook_conn
        self._shutdown = False
        self._active_thread = None
        self._hook_proc = None
        self._hook_conn = None
        self._server_sock = None
        self._key_held = False

    # ── Lifecycle ──────────────────────────────────────────────

    def setup_logging(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[
                RotatingFileHandler(
                    LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3,
                ),
                logging.StreamHandler(sys.stdout),
            ],
        )

    def write_pid(self):
        PID_FILE.write_text(str(os.getpid()))
        atexit.register(lambda: PID_FILE.unlink(missing_ok=True))

    # ── Hardware checks ────────────────────────────────────────

    def check_microphone(self) -> bool:
        try:
            default_input = sd.query_devices(kind="input")
            logger.info(f"Using input device: {default_input['name']}")
            return True
        except Exception as e:
            logger.error(f"No microphone found: {e}")
            self.notify("No microphone found", urgency="critical")
            return False

    def check_display(self):
        display_env = os.environ.get("DISPLAY")
        if not display_env:
            logger.warning("DISPLAY not set, trying :0")
            os.environ["DISPLAY"] = ":0"

    # ── Audio feedback ─────────────────────────────────────────

    def _play_sound(self, win_path: str):
        """Play a Windows WAV file non-blocking via PowerShell SoundPlayer."""
        try:
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-Command",
                 f"(New-Object Media.SoundPlayer '{win_path}').PlaySync()"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _beep(self, freq=660, duration=120):
        """Non-blocking beep via Windows PowerShell. Works regardless of focus."""
        try:
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-Command",
                 f"[Console]::Beep({freq},{duration})"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _send_hook_cmd(self, cmd: str):
        """Send a control command to keyhook.exe over the existing TCP connection."""
        with self._hook_lock:
            if self._hook_conn:
                try:
                    self._hook_conn.sendall((cmd + "\n").encode())
                except Exception as e:
                    logger.warning(f"Hook command {cmd!r} failed: {e}")

    # ── Notifications ──────────────────────────────────────────

    def notify(self, message, urgency="low"):
        try:
            subprocess.Popen(
                [
                    "notify-send", "Wispr Transcription", message,
                    "--urgency", urgency,
                    "--hint=string:x-dunst-stack-tag:wispr",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            logger.warning("notify-send not found")

    # ── Recording indicator ────────────────────────────────────

    def show_indicator(self):
        try:
            self.indicator_proc = subprocess.Popen(
                [sys.executable, str(INSTALL_DIR / "indicator.py")],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.warning(f"Could not show indicator: {e}")

    def hide_indicator(self):
        if self.indicator_proc:
            try:
                self.indicator_proc.terminate()
                self.indicator_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    self.indicator_proc.kill()
                    self.indicator_proc.wait(timeout=1)
                except Exception:
                    pass
            except Exception:
                pass
            self.indicator_proc = None

    # ── Audio stream ──────────────────────────────────────────

    def _close_stream(self):
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    # ── Audio recording ────────────────────────────────────────

    def start_recording(self):
        with self.lock:
            if self.recording or self.processing:
                return
            self.recording = True
            self.audio_frames = []

        try:
            self._play_sound("C:\\Windows\\Media\\Windows Notify.wav")
            self.notify("Recording...")
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="float32",
                callback=self._audio_callback,
                blocksize=1024,
            )
            self.stream.start()
            self.show_indicator()
            self._send_hook_cmd("RECORD_START")
            logger.info("Recording started")
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self.notify(f"Recording failed: {e}", urgency="critical")
            with self.lock:
                self.recording = False

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.warning(f"Audio status: {status}")
        if self.recording:
            self.audio_frames.append(indata.copy())

    def stop_recording_and_transcribe(self):
        with self.lock:
            if not self.recording:
                return
            self.recording = False
            self.processing = True

        self._close_stream()
        self.hide_indicator()
        self._send_hook_cmd("RECORD_STOP")

        try:
            if not self.audio_frames:
                logger.warning("No audio frames captured")
                self.notify("No audio captured")
                return

            audio = np.concatenate(self.audio_frames, axis=0)[:, 0]
            self.audio_frames = []
            duration = len(audio) / SAMPLE_RATE
            logger.info(f"Recording duration: {duration:.1f}s")

            if duration < MIN_RECORDING_SECONDS:
                logger.info("Recording too short, ignoring")
                self.notify("Recording too short")
                return

            if duration > MAX_RECORDING_SECONDS:
                logger.warning("Recording exceeds max, truncating")
                audio = audio[: int(MAX_RECORDING_SECONDS * SAMPLE_RATE)]

            # Check for silence
            rms = np.sqrt(np.dot(audio, audio) / len(audio))
            if rms < SILENCE_RMS_THRESHOLD:
                logger.info(f"Audio too quiet (RMS={rms:.6f}), likely silence")
                self.notify("No speech detected")
                return

            self.notify("Transcribing...")
            text = self.transcriber.transcribe(audio)

            if not text or not text.strip('. \t\n'):
                logger.info("No speech detected in transcription output")
                self.notify("No speech detected")
                return

            logger.info(f"Output: '{text}'")
            self.output_text(text)

        except Exception as e:
            logger.error(f"Transcription failed: {e}", exc_info=True)
            self.notify(f"Transcription error: {e}", urgency="critical")
        finally:
            self.audio_frames = []
            with self.lock:
                self.processing = False

    # ── Text output ────────────────────────────────────────────

    def output_text(self, text):
        """Copy text to clipboard and paste into focused window."""
        # Copy to Windows clipboard via clip.exe
        try:
            subprocess.run(
                ["clip.exe"],
                input=text.encode("utf-16-le"),
                check=True,
                timeout=5,
            )
            logger.info("Copied to Windows clipboard")
        except Exception as e:
            logger.error(f"Clipboard copy failed: {e}")
            return

        # Beep signals paste is incoming; brief delay so user can focus target window
        self._beep(440, 200)   # low beep = paste incoming
        time.sleep(0.3)

        # Paste via keyhook.exe SendInput (works in most apps including Windows Terminal).
        # Falls back to PowerShell SendKeys if the hook isn't connected.
        if self._hook_conn:
            self._send_hook_cmd("PASTE")
            logger.info("Pasted via keyboard hook")
        else:
            try:
                subprocess.run(
                    [
                        "powershell.exe", "-NoProfile", "-Command",
                        "Add-Type -AssemblyName System.Windows.Forms;"
                        "[System.Windows.Forms.SendKeys]::SendWait('^v')",
                    ],
                    timeout=5,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                logger.info("Pasted via PowerShell (fallback)")
            except Exception as e:
                logger.error(f"Paste failed: {e}")
                self.notify("Paste failed — text is in your clipboard")

    # ── Windows keyboard hook ─────────────────────────────────

    def _get_wsl_ip(self) -> str:
        """Return the WSL2 VM's IP address as reachable from Windows in NAT mode.

        In NAT mode, Windows can connect to WSL2 using the VM's eth0 IP.
        Detected by opening a dummy UDP socket and reading the outbound address.
        Falls back to 127.0.0.1 which works in mirrored networking mode.
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"

    def _run_keyboard_listener(self):
        """Capture hotkey via compiled C# keyboard hook over TCP.

        Architecture: Python starts a TCP server, then launches keyhook.exe
        via powershell.exe Start-Process. This runs keyhook.exe in the user's
        interactive session (Session 1), which is required for WH_KEYBOARD_LL
        to receive keyboard events. The IP of this WSL2 VM is passed so
        keyhook.exe can connect back in NAT networking mode.
        """
        vk_code = VK_CODES.get(HOTKEY)
        if vk_code is None:
            logger.error(f"Unknown hotkey: '{HOTKEY}' — "
                         f"valid options: {', '.join(VK_CODES.keys())}")
            self.notify(f"Unknown hotkey: {HOTKEY}", urgency="critical")
            return

        # Find the compiled hook executable
        exe_path = INSTALL_DIR / "keyhook.exe"
        if not exe_path.exists():
            logger.error("keyhook.exe not found — run ./install.sh first")
            self.notify("keyhook.exe not found — reinstall required",
                        urgency="critical")
            return

        # Copy to Windows temp to avoid UNC path trust restrictions.
        # Executables on \\wsl.localhost\ are treated as "network zone" by
        # Windows and may lose UIPI clearance needed for keyboard hooks.
        try:
            win_temp = subprocess.check_output(
                ["powershell.exe", "-NoProfile", "-Command",
                 "[System.IO.Path]::GetTempPath()"],
                text=True, timeout=10,
            ).strip().rstrip("\\")
            wsl_temp = subprocess.check_output(
                ["wslpath", "-u", win_temp], text=True,
            ).strip()
            dest = Path(wsl_temp) / "wispr_keyhook.exe"
            shutil.copy2(exe_path, dest)
            win_exe_path = subprocess.check_output(
                ["wslpath", "-w", str(dest)], text=True,
            ).strip()
            logger.info(f"Copied keyhook.exe to {win_exe_path}")
        except Exception as e:
            logger.error(f"Could not copy keyhook.exe to Windows temp: {e}")
            return

        # Get WSL2's IP so keyhook.exe can connect back in NAT networking mode
        wsl_ip = self._get_wsl_ip()
        logger.info(f"WSL2 IP for hook callback: {wsl_ip}")

        # Start TCP server for hook communication
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind(('0.0.0.0', 0))
        self._server_sock.listen(1)
        port = self._server_sock.getsockname()[1]
        self._server_sock.settimeout(30)
        logger.info(f"Keyboard hook TCP server listening on port {port}")

        # Launch keyhook.exe via PowerShell Start-Process. This runs the exe
        # in the user's interactive session (Session 1), which is required for
        # WH_KEYBOARD_LL to receive keyboard events. schtasks /Run would put
        # it in Session 0 (service session) where the hook gets no input.
        logger.info(f"Launching keyboard hook for {HOTKEY} "
                    f"(VK=0x{vk_code:02X}) via Start-Process")
        ps_cmd = (
            f'Start-Process -FilePath "{win_exe_path}" '
            f'-ArgumentList "{wsl_ip} {port} {vk_code}" '
            f'-WindowStyle Hidden'
        )
        try:
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive",
                 "-Command", ps_cmd],
                capture_output=True, timeout=15,
            )
        except Exception as e:
            logger.error(f"Failed to launch keyboard hook: {e}")
            self.notify("Keyboard hook launch failed — see logs",
                        urgency="critical")
            self._server_sock.close()
            return

        # Wait for the hook process to connect
        try:
            self._hook_conn, addr = self._server_sock.accept()
            logger.info(f"Keyboard hook connected from {addr}")
        except socket.timeout:
            logger.error("Keyboard hook did not connect within 30s")
            self.notify("Keyboard hook timeout — see logs", urgency="critical")
            self._server_sock.close()
            return
        finally:
            self._server_sock.close()
            self._server_sock = None

        # Read events from TCP connection
        try:
            reader = self._hook_conn.makefile('r')
            first_line = reader.readline().strip()
            if first_line == "HOOK_FAILED":
                logger.error("Keyboard hook failed to install")
                self.notify("Keyboard hook failed — see logs",
                            urgency="critical")
                return
            if first_line != "HOOK_READY":
                logger.error(f"Unexpected hook response: '{first_line}'")
                self.notify("Keyboard hook error — see logs",
                            urgency="critical")
                return

            logger.info("Windows keyboard hook active")

            for line in reader:
                if self._shutdown:
                    break
                line = line.strip()
                if not line:
                    continue
                if line == "KEY_DOWN":
                    if not self._key_held:
                        self._key_held = True
                        self.start_recording()
                elif line == "KEY_UP":
                    if self._key_held:
                        self._key_held = False
                        t = threading.Thread(
                            target=self.stop_recording_and_transcribe,
                            daemon=False,
                        )
                        t.start()
                        self._active_thread = t
        except Exception as e:
            if not self._shutdown:
                logger.error(f"Keyboard hook read error: {e}")
        finally:
            self._stop_hook()

    def _stop_hook(self):
        # Send quit signal to the hook process
        self._send_hook_cmd("QUIT")
        if self._hook_conn:
            try:
                self._hook_conn.close()
            except Exception:
                pass
            self._hook_conn = None
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None

    # ── Main loop ──────────────────────────────────────────────

    def run(self):
        self.setup_logging()
        self.write_pid()
        self.check_display()

        logger.info("=" * 50)
        logger.info("Wispr Transcription starting")
        logger.info(f"PID: {os.getpid()}")

        if not self.check_microphone():
            sys.exit(1)

        if not OPENAI_API_KEY:
            logger.error("OPENAI_API_KEY not set — export it in your shell")
            self.notify("OPENAI_API_KEY not set", urgency="critical")
            sys.exit(1)

        try:
            self.transcriber.load_model()
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}", exc_info=True)
            self.notify(f"OpenAI init failed: {e}", urgency="critical")
            sys.exit(1)

        self.notify(f"Ready! Hold {HOTKEY} to dictate.")
        logger.info("Ready — listening for hotkey")

        def shutdown(signum, frame):
            logger.info("Shutting down...")
            self._shutdown = True
            self._stop_hook()

        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)

        self._run_keyboard_listener()

        # Wait for any in-progress transcription to finish
        if self._active_thread and self._active_thread.is_alive():
            logger.info("Waiting for transcription to finish...")
            self._active_thread.join(timeout=30)

        self.hide_indicator()
        self._close_stream()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    WisprDaemon().run()
