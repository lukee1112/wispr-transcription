"""Whisper transcription and text cleaning."""
import re
import logging
import threading
import time

import numpy as np
import whisper
import torch

from config import WHISPER_MODEL, WHISPER_LANGUAGE, FILLER_WORDS, CONTEXT_FILLERS

logger = logging.getLogger(__name__)


class Transcriber:
    def __init__(self):
        self.model = None
        self.device = None
        self._lock = threading.Lock()

    def load_model(self):
        """Load Whisper model, using GPU if available."""
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Loading Whisper '{WHISPER_MODEL}' model on {self.device}...")

        start = time.time()
        self.model = whisper.load_model(WHISPER_MODEL, device=self.device)
        elapsed = time.time() - start
        logger.info(f"Model loaded in {elapsed:.1f}s")

        if self.device == "cuda":
            gpu_name = torch.cuda.get_device_name(0)
            logger.info(f"Using GPU: {gpu_name}")
        else:
            logger.info("No GPU detected, using CPU (transcription will be slower)")

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio numpy array to cleaned text. Thread-safe."""
        if self.model is None:
            raise RuntimeError("Model not loaded")

        with self._lock:
            start = time.time()
            result = self.model.transcribe(
                audio,
                language=WHISPER_LANGUAGE,
                fp16=(self.device == "cuda"),
                task="transcribe",
            )
            elapsed = time.time() - start

        text = result["text"].strip()
        preview = (text[:80] + "...") if len(text) > 80 else text
        logger.info(f"Transcribed in {elapsed:.1f}s: '{preview}'")

        if not text:
            return ""

        return self.clean_text(text)

    def clean_text(self, text: str) -> str:
        """Remove filler words and clean punctuation."""
        # Remove always-filler words (um, uh, etc.)
        # Remove always-filler words (um, uh, etc.)
        for filler in FILLER_WORDS:
            pattern = re.compile(
                r',?\s*\b' + re.escape(filler) + r'\b\s*,?',
                re.IGNORECASE,
            )

            def _replace(m, _text=text):
                # Preserve filler if preceded by a digit (measurement: "100 mm")
                before = _text[:m.start()].rstrip(' ,')
                if before and before[-1].isdigit():
                    return m.group(0)
                return ' '

            text = pattern.sub(_replace, text)

        # Remove context-dependent fillers only in filler positions
        for filler in CONTEXT_FILLERS:
            escaped = re.escape(filler)
            # Between commas: ", like, "
            text = re.sub(
                r',\s*\b' + escaped + r'\b\s*,', ',',
                text, flags=re.IGNORECASE,
            )
            # At sentence start: "Like, ..."
            text = re.sub(
                r'(?:^|(?<=\.\s))' + escaped + r',?\s*',
                '', text, flags=re.IGNORECASE,
            )
            # Before sentence end: "... like."
            text = re.sub(
                r',?\s*\b' + escaped + r'\b\s*(?=[.!?])',
                '', text, flags=re.IGNORECASE,
            )

        # Clean up whitespace and punctuation artifacts
        text = re.sub(r'\s{2,}', ' ', text)
        text = re.sub(r'\s+([.,!?;:])', r'\1', text)
        text = re.sub(r',\s*,', ',', text)
        text = re.sub(r'^\s*,\s*', '', text)
        text = re.sub(r',\s*$', '.', text)

        text = text.strip()

        # Capitalize first letter
        if text:
            text = text[0].upper() + text[1:]

        # Ensure ending punctuation
        if text and text[-1] not in '.!?':
            text += '.'

        return text
