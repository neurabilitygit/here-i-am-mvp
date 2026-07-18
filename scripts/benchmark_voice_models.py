#!/usr/bin/env python3
"""Compare MLX Qwen3-TTS variants on the same shared-reference sentence batch."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import soundfile as sf


TEXTS = [
    'I remember how much the small details mattered, especially the ordinary moments that nobody thought to write down at the time.',
    'A familiar room, a particular expression, or the rhythm of a conversation can bring an entire period of life back into focus.',
    'That is why these recordings feel valuable to me: they preserve not only events, but also the way I understood them.',
    'When the answer is spoken aloud, I want it to sound measured, recognizable, and naturally connected from one thought to the next.',
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--reference-audio', required=True)
    parser.add_argument('--reference-text-file', required=True)
    parser.add_argument('--output')
    args = parser.parse_args()

    from mlx_audio.tts.utils import load_model

    load_started = time.perf_counter()
    model = load_model(args.model)
    load_seconds = time.perf_counter() - load_started
    parts: list[list[np.ndarray]] = [[] for _ in TEXTS]
    generation_started = time.perf_counter()
    reference_text = Path(args.reference_text_file).read_text(encoding='utf-8').strip()
    for result in model.batch_generate(
        texts=TEXTS,
        ref_audio=args.reference_audio,
        ref_text=reference_text,
        lang_code='English',
        max_tokens=240,
        stream=True,
        streaming_interval=.8,
        verbose=False,
    ):
        parts[int(result.sequence_idx)].append(np.asarray(result.audio, dtype=np.float32).reshape(-1))
    generation_seconds = time.perf_counter() - generation_started
    sample_rate = int(model.sample_rate)
    durations = [sum(value.size for value in sequence) / sample_rate for sequence in parts]
    if args.output:
        pause = np.zeros(int(sample_rate * 0.11), dtype=np.float32)
        completed = [np.concatenate(sequence) for sequence in parts if sequence]
        stitched: list[np.ndarray] = []
        for index, audio in enumerate(completed):
            if index:
                stitched.append(pause)
            stitched.append(audio)
        sf.write(args.output, np.concatenate(stitched), sample_rate)
    print(json.dumps({
        'model': args.model,
        'load_seconds': round(load_seconds, 2),
        'generation_seconds': round(generation_seconds, 2),
        'audio_seconds': round(sum(durations), 2),
        'elapsed_per_audio_second': round(generation_seconds / max(sum(durations), .001), 3),
        'segments': len(TEXTS),
        'completed_segments': sum(bool(sequence) for sequence in parts),
        'output': args.output or '',
    }))


if __name__ == '__main__':
    main()
