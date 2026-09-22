"""Evaluate exact span/type quality. Never claim equivalence to the organizer metric."""
import argparse
import json
from collections import Counter
from pathlib import Path

from alfa_pii.config import Consumer
from alfa_pii.detection.engine import Detector, resolve
from alfa_pii.domain import Kind
from alfa_pii.service import protect
from alfa_pii.transformation.masking import restore


def evaluate(rows: list[dict], use_ner: bool) -> dict:
    detector = Detector(use_ner)
    counts = {str(kind): Counter(tp=0, fp=0, fn=0) for kind in Kind}
    exact_documents = roundtrips = negative_count = negative_false_positives = leaked_documents = 0
    for row in rows:
        text = row["text"]
        expected = {(e["kind"], e["start"], e["end"]) for e in row["entities"]}
        spans = resolve(detector.detect(text))
        actual = {(str(e.kind), e.start, e.end) for e in spans}
        for kind, _, _ in expected & actual:
            counts.setdefault(kind, Counter())["tp"] += 1
        for kind, _, _ in actual - expected:
            counts.setdefault(kind, Counter())["fp"] += 1
        for kind, _, _ in expected - actual:
            counts.setdefault(kind, Counter())["fn"] += 1
        exact_documents += expected == actual
        if not expected:
            negative_count += 1
            negative_false_positives += bool(actual)
        covered = set()
        for e in spans:
            covered.update(range(e.start, e.end))
        leaked_documents += any(i not in covered and text[i].isalnum()
                                for _, a, b in expected for i in range(a, b))
        result = protect(detector, text, Consumer(id="quality"), "typed_tokens")
        roundtrips += restore(result.text, result) == text
    def score(c: Counter) -> dict:
        p = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else 1.0
        r = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else 1.0
        return dict(c, precision=p, recall=r, f1=2*p*r/(p+r) if p+r else 0.0)
    totals = Counter()
    for c in counts.values():
        totals.update(c)
    return {"documents": len(rows), "use_ner": use_ner,
            "metric": "exact_span_and_type; NOT organizer scoring",
            "provenance": "Provided corpus; human label review and independent holdout are separate requirements",
            "micro": score(totals), "per_category": {k: score(c) for k, c in counts.items()},
            "exact_documents": exact_documents, "roundtrip_exact": roundtrips,
            "negative_documents": negative_count, "negative_false_positives": negative_false_positives,
            "documents_with_uncovered_pii": leaked_documents}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rules-only", action="store_true")
    parser.add_argument("--require-95", action="store_true")
    parser.add_argument("--minimum-support", type=int, default=5)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.corpus.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise SystemExit("Empty corpus")
    report = evaluate(rows, not args.rules_only)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"documents": report["documents"], "micro": report["micro"], "roundtrip_exact": report["roundtrip_exact"]}))
    if args.require_95 and (any(v["precision"] < .95 or v["recall"] < .95 or v["tp"] + v["fn"] < args.minimum_support for v in report["per_category"].values())
                            or report["roundtrip_exact"] != len(rows) or report["documents_with_uncovered_pii"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
