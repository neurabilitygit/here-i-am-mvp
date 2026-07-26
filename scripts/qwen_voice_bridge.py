"""Native, localhost-only Qwen3-TTS voice-cloning bridge for Apple Silicon.

Install in a dedicated Python 3.12 environment with requirements-voice.txt. The
model is loaded lazily so /health remains available before weights are ready.
"""
from __future__ import annotations

import io
import gc
import os
import threading
from pathlib import Path

import soundfile as sf
import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field


MODEL_ID = os.environ.get('QWEN_TTS_MODEL', 'Qwen/Qwen3-TTS-12Hz-0.6B-Base')
PREFERRED_DEVICE = os.environ.get('QWEN_TTS_DEVICE', 'cpu').lower()
app = FastAPI(title='Here I Am local voice bridge')
_model = None
_model_device = None
_voice_prompt = None
_voice_prompt_key = None
_model_lock = threading.Lock()
_generation_lock = threading.Lock()


class SynthesisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    reference_audio: str
    reference_text: str = ''
    speed: float = Field(default=1.0, ge=0.7, le=1.3)


def load_model(force_cpu: bool = False):
    global _model, _model_device, _voice_prompt, _voice_prompt_key
    with _model_lock:
        requested_device = 'cpu'
        if not force_cpu and PREFERRED_DEVICE == 'mps' and torch.backends.mps.is_available():
            requested_device = 'mps'
        if _model is not None and _model_device == requested_device:
            return _model
        if _model is not None:
            del _model
            _model = None
            _voice_prompt = None
            _voice_prompt_key = None
            gc.collect()
            if torch.backends.mps.is_available():
                torch.mps.empty_cache()
        try:
            from qwen_tts import Qwen3TTSModel
        except ImportError as exc:
            raise RuntimeError('qwen-tts is not installed in the voice environment') from exc
        device = requested_device
        # Qwen sampling can produce NaN/inf probabilities in float16 on MPS.
        # Full precision is still GPU-accelerated and avoids the slow CPU path.
        dtype = torch.float32
        _model = Qwen3TTSModel.from_pretrained(
            MODEL_ID,
            device_map=device,
            dtype=dtype,
            attn_implementation='sdpa',
        )
        _model_device = device
        return _model


def generate(model, request: SynthesisRequest):
    global _voice_prompt, _voice_prompt_key
    reference = Path(request.reference_audio)
    prompt_key = (
        str(reference.resolve()),
        reference.stat().st_mtime_ns,
        request.reference_text,
        _model_device,
    )
    if _voice_prompt is None or _voice_prompt_key != prompt_key:
        _voice_prompt = model.create_voice_clone_prompt(
            ref_audio=str(reference),
            ref_text=request.reference_text or None,
            x_vector_only_mode=not bool(request.reference_text.strip()),
        )
        _voice_prompt_key = prompt_key
    return model.generate_voice_clone(
        text=request.text,
        language='English',
        voice_clone_prompt=_voice_prompt,
    )


@app.get('/health')
def health():
    return {
        'status': 'ok',
        'engine': 'qwen3-tts',
        'model': MODEL_ID,
        'model_loaded': _model is not None,
        'device': _model_device or ('mps' if PREFERRED_DEVICE == 'mps' and torch.backends.mps.is_available() else 'cpu'),
    }


@app.post('/warm')
def warm():
    try:
        load_model()
        return {'status': 'ready', 'model': MODEL_ID}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post('/synthesize')
def synthesize(request: SynthesisRequest):
    reference = Path(request.reference_audio)
    if not reference.exists():
        raise HTTPException(status_code=404, detail='Reference audio was not found on the host')
    if not _generation_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail='The local voice is already preparing another answer')
    try:
        model = load_model()
        try:
            wavs, sample_rate = generate(model, request)
        except RuntimeError as exc:
            numerical_failure = any(token in str(exc).lower() for token in ('nan', 'inf', 'probability tensor'))
            if _model_device != 'mps' or not numerical_failure:
                raise
            model = load_model(force_cpu=True)
            wavs, sample_rate = generate(model, request)
        buffer = io.BytesIO()
        sf.write(buffer, wavs[0], sample_rate, format='WAV')
        return Response(buffer.getvalue(), media_type='audio/wav', headers={'X-Voice-Engine': 'qwen3-tts'})
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f'Local voice generation failed: {exc}') from exc
    finally:
        _generation_lock.release()
