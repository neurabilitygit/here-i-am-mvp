#!/usr/bin/env python3
"""Compare repeated unload-after-query and short-residency local embeddings.

Uses synthetic text, changes no vectors or preferences, and releases the tested
model afterward. Run only during an idle maintenance window, not during chat or
indexing. Model-loading time is reported separately, never inferred from totals.
"""
import argparse
import json
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=11434)
    parser.add_argument('--model', default='embeddinggemma')
    parser.add_argument('--iterations', type=int, choices=range(2, 6), default=3)
    parser.add_argument('--confirm-idle', action='store_true', required=True)
    args = parser.parse_args()
    url = f'http://127.0.0.1:{args.port}/api/embed'
    def post(text, keep_alive):
        request = urllib.request.Request(url, data=json.dumps({'model': args.model, 'input': text, 'keep_alive': keep_alive}).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)
    rows = []
    try:
        post('', 0)
        for policy in (0, '5m'):
            for iteration in range(args.iterations):
                started = time.perf_counter()
                result = post('What do my recorded memories say about childhood pets?', policy)
                rows.append({
                    'keep_alive': policy, 'iteration': iteration + 1,
                    'wall_seconds': time.perf_counter() - started,
                    'load_seconds': result.get('load_duration', 0) / 1e9 if 'load_duration' in result else None,
                    'total_seconds': result.get('total_duration', 0) / 1e9 if 'total_duration' in result else None,
                    'dimensions': len(result['embeddings'][0]),
                })
    finally:
        post('', 0)
    print(json.dumps({'model': args.model, 'synthetic_text': True, 'results': rows}, indent=2))


if __name__ == '__main__':
    main()
