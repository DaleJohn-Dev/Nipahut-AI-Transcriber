"""Score only explicitly annotated regions; prints a compact report by default.

Example:
  python scripts/evaluate_reference.py reference.rttm recording.json \
    --region 0 30 --human-reference --output test-results/reference-score.json

Reference RTTM/JSON must contain each simultaneous speaker on a separate turn.
Every silence interval inside --region is assumed human-verified silence.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.evaluation import load_turns, score_diarization


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('hypothesis', type=Path)
    parser.add_argument('--region', nargs=2, type=float, action='append', required=True, metavar=('START', 'END'))
    parser.add_argument('--reference-recording-id')
    parser.add_argument('--hypothesis-recording-id')
    parser.add_argument('--human-reference', action='store_true', help='Assert labels and silence within scoring regions were independently checked by a human.')
    mapping_args = parser.add_mutually_exclusive_group()
    mapping_args.add_argument('--identity-labels', action='store_true', help='Keep labels fixed: score known identities instead of optimally permuting anonymous clusters.')
    mapping_args.add_argument('--mapping', type=Path, help='JSON object mapping hypothesis IDs to verified reference IDs; must be one-to-one.')
    parser.add_argument('--output', type=Path, help='Optional small JSON report. No audio files are created.')
    args = parser.parse_args()
    try:
        reference = load_turns(args.reference, args.reference_recording_id)
        mapping = json.loads(args.mapping.read_text(encoding='utf-8')) if args.mapping else None
        if args.identity_labels:
            mapping = {t['speaker_id']: t['speaker_id'] for t in reference}
        result = score_diarization(reference, load_turns(args.hypothesis, args.hypothesis_recording_id),
            args.region, reference_is_human=args.human_reference, fixed_mapping=mapping)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    report = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        args.output.write_text(report + '\n', encoding='utf-8')
    print(report)
    return 0 if result['status'] == 'scored' else 2


if __name__ == '__main__':
    raise SystemExit(main())
