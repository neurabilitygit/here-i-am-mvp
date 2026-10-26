#!/usr/bin/env python3
"""Read-only memoir RAG quality evaluation.

Input is JSONL with: id, question, expected_session_ids, and should_abstain.
Use --generate to include the configured answer provider; retrieval-only mode is
the safe default and never changes the library or Chroma.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

from services.pipeline import answer_question, prepare_answer  # noqa: E402


UNKNOWN = "I don't know the answer based on what I've recorded."


def load_cases(path: Path) -> list[dict]:
    cases = []
    for line_number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value.get('question'), str) or not value['question'].strip():
            raise ValueError(f'Line {line_number} requires a question')
        value['expected_session_ids'] = list(value.get('expected_session_ids') or [])
        value['should_abstain'] = bool(value.get('should_abstain'))
        cases.append(value)
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cases', type=Path)
    parser.add_argument('--generate', action='store_true')
    args = parser.parse_args()
    cases = load_cases(args.cases)
    rows = []
    retrieval_cases = 0
    recall_hits = 0
    reciprocal_rank = 0.0
    gate_abstention_correct = 0
    abstention_correct = 0
    for case in cases:
        prepared = prepare_answer(case['question'])
        retrieved = [source.session_id for source in prepared.sources]
        expected = set(case['expected_session_ids'])
        ranks = [index + 1 for index, session_id in enumerate(retrieved) if session_id in expected]
        retrieval_hit = bool(ranks) if expected else None
        if expected:
            retrieval_cases += 1
            recall_hits += int(retrieval_hit)
            reciprocal_rank += 1 / min(ranks) if ranks else 0.0
        direct_abstention = prepared.direct_answer == UNKNOWN
        gate_correct = direct_abstention == case['should_abstain']
        gate_abstention_correct += int(gate_correct)
        row = {
            'id': case.get('id', ''),
            'mode': prepared.mode,
            'retrieved_session_ids': retrieved,
            'retrieval_hit': retrieval_hit,
            'reciprocal_rank': 1 / min(ranks) if ranks else 0.0,
            'direct_abstention': direct_abstention,
            'retrieval_gate_abstention_correct': gate_correct,
        }
        if args.generate:
            response = answer_question(case['question'])
            abstained = response.answer.strip() == UNKNOWN
            expected_abstention = case['should_abstain']
            row['abstained'] = abstained
            row['abstention_correct'] = abstained == expected_abstention
            row['answer_characters'] = len(response.answer)
            abstention_correct += int(row['abstention_correct'])
        rows.append(row)
    count = len(cases)
    report = {
        'cases': count,
        'retrieval_cases': retrieval_cases,
        'generation_enabled': args.generate,
        'retrieval_recall': recall_hits / retrieval_cases if retrieval_cases else None,
        'mean_reciprocal_rank': reciprocal_rank / retrieval_cases if retrieval_cases else None,
        'retrieval_gate_abstention_accuracy': gate_abstention_correct / count if count else None,
        'abstention_accuracy': abstention_correct / count if args.generate and count else None,
        'results': rows,
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
