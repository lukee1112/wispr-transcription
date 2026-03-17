"""Whisper transcription via OpenAI API and text cleaning."""
import io
import re
import logging
import threading
import time
import wave

import numpy as np
from openai import OpenAI

from config import OPENAI_API_KEY, WHISPER_LANGUAGE, SAMPLE_RATE, FILLER_WORDS, CONTEXT_FILLERS

logger = logging.getLogger(__name__)

# Pre-compiled regex patterns for filler removal (static, built once)
_FILLER_PATTERNS = [
    re.compile(r',?\s*\b' + re.escape(f) + r'\b\s*,?', re.IGNORECASE)
    for f in FILLER_WORDS
]

_CONTEXT_PATTERNS = []
for _f in CONTEXT_FILLERS:
    _e = re.escape(_f)
    _CONTEXT_PATTERNS.append((
        re.compile(r',\s*\b' + _e + r'\b\s*,', re.IGNORECASE),
        re.compile(r'(?:^|(?<=\.\s))' + _e + r',?\s*', re.IGNORECASE),
        re.compile(r',?\s*\b' + _e + r'\b\s*(?=[.!?])', re.IGNORECASE),
    ))

_RE_MULTI_SPACE = re.compile(r'\s{2,}')
_RE_SPACE_BEFORE_PUNCT = re.compile(r'\s+([.,!?;:])')
_RE_DOUBLE_COMMA = re.compile(r',\s*,')
_RE_LEADING_COMMA = re.compile(r'^\s*,\s*')
_RE_TRAILING_COMMA = re.compile(r',\s*$')


class Transcriber:
    def __init__(self):
        self._lock = threading.Lock()
        self._client = None

    def load_model(self):
        """Validate OpenAI API key and initialize client."""
        if not OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY not set. Export it in your environment or "
                "add it to a .env file."
            )
        self._client = OpenAI(api_key=OPENAI_API_KEY)
        # Quick validation — list models would work but is slow.
        # We'll find out on first transcription if the key is bad.
        logger.info("OpenAI Whisper API client ready")

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio numpy array to cleaned text via OpenAI API. Thread-safe."""
        if self._client is None:
            raise RuntimeError("Client not initialized — call load_model() first")

        # Convert float32 numpy array to WAV bytes for the API
        wav_buf = io.BytesIO()
        audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
        with wave.open(wav_buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_int16.tobytes())
        wav_buf.seek(0)
        wav_buf.name = "audio.wav"  # OpenAI client needs a filename

        with self._lock:
            start = time.time()
            response = self._client.audio.transcriptions.create(
                model="whisper-1",
                file=wav_buf,
                language=WHISPER_LANGUAGE,
            )
            elapsed = time.time() - start

        text = response.text.strip()
        preview = (text[:80] + "...") if len(text) > 80 else text
        logger.info(f"Transcribed in {elapsed:.1f}s: '{preview}'")

        if not text:
            return ""

        return self.clean_text(text)

    def clean_text(self, text: str) -> str:
        """Remove filler words and clean punctuation."""
        # Remove always-filler words (um, uh, etc.)
        for pattern in _FILLER_PATTERNS:

            def _replace(m):
                # Preserve filler if preceded by a digit (measurement: "100 mm")
                before = m.string[:m.start()].rstrip(' ,')
                if before and before[-1].isdigit():
                    return m.group(0)
                return ' '

            text = pattern.sub(_replace, text)

        # Remove context-dependent fillers only in filler positions
        for between_commas, at_start, before_end in _CONTEXT_PATTERNS:
            text = between_commas.sub(',', text)
            text = at_start.sub('', text)
            text = before_end.sub('', text)

        # Clean up whitespace and punctuation artifacts
        text = _RE_MULTI_SPACE.sub(' ', text)
        text = _RE_SPACE_BEFORE_PUNCT.sub(r'\1', text)
        text = _RE_DOUBLE_COMMA.sub(',', text)
        text = _RE_LEADING_COMMA.sub('', text)
        text = _RE_TRAILING_COMMA.sub('.', text)

        text = text.strip()

        # Capitalize first letter
        if text:
            text = text[0].upper() + text[1:]

        # Ensure ending punctuation
        if text and text[-1] not in '.!?':
            text += '.'

        return text
