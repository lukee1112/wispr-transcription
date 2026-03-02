#!/usr/bin/env python3
"""Wispr Transcription - Local voice dictation daemon.

Hold a hotkey to record, release to transcribe and type into the focused window.
Uses X11 key grabs (works on XWayland/WSLg) instead of XRecord.
"""
import os
import re
import sys
import signal
import subprocess
import threading
import time
import logging
import atexit
from logging.handlers import RotatingFileHandler

import numpy as np
import sounddevice as sd
from Xlib import display, X, XK

from config import (
    HOTKEY, SAMPLE_RATE, CHANNELS,
    MIN_RECORDING_SECONDS, MAX_RECORDING_SECONDS,
    DATA_DIR, LOG_FILE, PID_FILE, INSTALL_DIR,
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
        self._shutdown = False
        self._active_thread = None

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

    def check_display(self) -> bool:
        display_env = os.environ.get("DISPLAY")
        if not display_env:
            logger.warning("DISPLAY not set, trying :0")
            os.environ["DISPLAY"] = ":0"
        return True

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

    # ── Audio recording ────────────────────────────────────────

    def start_recording(self):
        with self.lock:
            if self.recording or self.processing:
                return
            self.recording = True
            self.audio_frames = []

        try:
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="float32",
                callback=self._audio_callback,
                blocksize=1024,
            )
            self.stream.start()
            self.show_indicator()
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

        # Stop audio stream BEFORE reading audio_frames
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

        self.hide_indicator()

        try:
            if not self.audio_frames:
                logger.warning("No audio frames captured")
                self.notify("No audio captured")
                return

            audio = np.concatenate(self.audio_frames, axis=0).flatten()
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
            rms = np.sqrt(np.mean(audio ** 2))
            if rms < 0.001:
                logger.info(f"Audio too quiet (RMS={rms:.6f}), likely silence")
                self.notify("No speech detected")
                return

            self.notify("Transcribing...")
            text = self.transcriber.transcribe(audio)

            if not text or re.fullmatch(r'[.\s]*', text):
                logger.info("No speech detected in transcription output")
                self.notify("No speech detected")
                return

            logger.info(f"Output: '{text}'")
            self.output_text(text)

        except Exception as e:
            logger.error(f"Transcription failed: {e}", exc_info=True)
            self.notify(f"Transcription error: {e}", urgency="critical")
        finally:
            with self.lock:
                self.processing = False

    # ── Text output ────────────────────────────────────────────

    def _copy_to_clipboard(self, text):
        """Copy text to X11 clipboard. Returns True on success."""
        for cmd in [
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
        ]:
            try:
                subprocess.run(
                    cmd, input=text.encode("utf-8"),
                    check=True, timeout=5,
                )
                logger.info(f"Copied to clipboard ({cmd[0]})")
                return True
            except FileNotFoundError:
                continue
            except Exception as e:
                logger.error(f"Clipboard copy failed ({cmd[0]}): {e}")
                continue
        logger.error("No clipboard tool available")
        return False

    def output_text(self, text):
        """Copy text to clipboard and paste into focused window."""
        if not self._copy_to_clipboard(text):
            return

        # Small delay so the released hotkey doesn't interfere
        time.sleep(0.15)

        # Paste via Ctrl+V (handles Unicode correctly, unlike xdotool type)
        try:
            subprocess.run(
                ["xdotool", "key", "--clearmodifiers", "ctrl+v"],
                check=True,
                timeout=5,
            )
            logger.info("Pasted into focused window")
        except FileNotFoundError:
            logger.error("xdotool not found — text is in your clipboard")
            self.notify("xdotool not found — text copied to clipboard only",
                        urgency="critical")
        except Exception as e:
            logger.error(f"xdotool paste failed: {e}")
            self.notify("Paste failed — text is in your clipboard")

    # ── X11 keyboard listener ─────────────────────────────────

    def _run_keyboard_listener(self):
        """Listen for hotkey using X11 key grabs (works on XWayland/WSLg)."""
        d = display.Display()
        root = d.screen().root

        keysym = XK.string_to_keysym(HOTKEY)
        if keysym == 0:
            logger.error(f"Unknown hotkey keysym: '{HOTKEY}'")
            self.notify(f"Unknown hotkey: {HOTKEY}", urgency="critical")
            return

        keycode = d.keysym_to_keycode(keysym)
        if keycode == 0:
            logger.error(f"Could not map keysym to keycode: '{HOTKEY}'")
            self.notify(f"Could not map hotkey: {HOTKEY}", urgency="critical")
            return

        logger.info(f"Hotkey: {HOTKEY} (keycode={keycode})")

        # Grab the key globally — works on XWayland unlike XRecord
        root.grab_key(keycode, X.AnyModifier, True,
                      X.GrabModeAsync, X.GrabModeAsync)
        d.sync()
        logger.info("X11 key grab active")

        try:
            import select
            fd = d.fileno()

            while not self._shutdown:
                readable, _, _ = select.select([fd], [], [], 0.25)
                if not readable:
                    continue

                n = d.pending_events()
                for _ in range(n):
                    event = d.next_event()

                    if event.type == X.KeyPress:
                        # Filter auto-repeat: if next event is KeyRelease
                        # for the same key followed by KeyPress, it's repeat
                        if d.pending_events() > 0:
                            next_ev = d.next_event()
                            if (next_ev.type == X.KeyRelease
                                    and next_ev.detail == keycode):
                                # Auto-repeat release, skip
                                continue
                            # Not repeat — process the peeked event
                            if next_ev.type == X.KeyRelease and next_ev.detail == keycode:
                                self._on_key_release()
                            elif next_ev.type == X.KeyPress and next_ev.detail == keycode:
                                pass  # Already recording
                        self._on_key_press()

                    elif event.type == X.KeyRelease:
                        # Check for auto-repeat: peek next event
                        if d.pending_events() > 0:
                            next_ev = d.next_event()
                            if (next_ev.type == X.KeyPress
                                    and next_ev.detail == keycode):
                                # Auto-repeat, ignore both events
                                continue
                            # Not repeat — put back by processing it
                            if next_ev.type == X.KeyPress and next_ev.detail == keycode:
                                self._on_key_press()
                            elif next_ev.type == X.KeyRelease and next_ev.detail == keycode:
                                self._on_key_release()
                        self._on_key_release()

        finally:
            try:
                root.ungrab_key(keycode, X.AnyModifier)
                d.sync()
            except Exception:
                pass
            d.close()

    def _on_key_press(self):
        self.start_recording()

    def _on_key_release(self):
        t = threading.Thread(
            target=self.stop_recording_and_transcribe,
            daemon=False,
        )
        t.start()
        self._active_thread = t

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

        self.notify("Loading Whisper model (this may take a moment)...")
        try:
            self.transcriber.load_model()
        except Exception as e:
            logger.error(f"Failed to load model: {e}", exc_info=True)
            self.notify(f"Model load failed: {e}", urgency="critical")
            sys.exit(1)

        self.notify(f"Ready! Hold {HOTKEY} to dictate.")
        logger.info("Ready — listening for hotkey")

        def shutdown(signum, frame):
            logger.info("Shutting down...")
            self._shutdown = True

        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)

        self._run_keyboard_listener()

        # Wait for any in-progress transcription to finish
        if self._active_thread and self._active_thread.is_alive():
            logger.info("Waiting for transcription to finish...")
            self._active_thread.join(timeout=30)

        self.hide_indicator()
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
        logger.info("Shutdown complete")


if __name__ == "__main__":
    WisprDaemon().run()
