"""Validate a private, manually reviewed JSONL holdout without printing examples."""
import argparse
import json
from pathlib import Path

from alfa_pii.domain import Kind

KINDS = {str(kind) for kind in Kind}


def validate_rows(rows: list[dict], minimum_per_kind: int = 10,
                  minimum_negatives: int = 20) -> dict:
    if minimum_per_kind < 1 or minimum_negatives < 0:
        raise ValueError("Invalid support thresholds")
    seen_ids: set[str] = set()
    seen_texts: set[str] = set()
    support = {kind: 0 for kind in sorted(KINDS)}
    negatives = 0
    for line, row in enumerate(rows, 1):
        if not isinstance(row, dict) or set(row) != {"id", "category", "text", "entities"}:
            raise ValueError(f"Line {line}: invalid row fields")
        identifier, category, text, entities = (
            row["id"], row["category"], row["text"], row["entities"]
        )
        if not isinstance(identifier, str) or not identifier or identifier in seen_ids:
            raise ValueError(f"Line {line}: invalid or duplicate id")
        if not isinstance(category, str) or category not in KINDS | {"NEGATIVE"}:
            raise ValueError(f"Line {line}: invalid category")
        if not isinstance(text, str) or not text or text in seen_texts:
            raise ValueError(f"Line {line}: empty or duplicate text")
        if not isinstance(entities, list):
            raise ValueError(f"Line {line}: entities must be a list")
        seen_ids.add(identifier)
        seen_texts.add(text)
        spans: list[tuple[int, int]] = []
        kinds_in_document: set[str] = set()
        for entity in entities:
            if not isinstance(entity, dict) or set(entity) != {"kind", "start", "end"}:
                raise ValueError(f"Line {line}: invalid entity fields")
            kind, start, end = entity["kind"], entity["start"], entity["end"]
            if (not isinstance(kind, str) or kind not in KINDS
                    or type(start) is not int or type(end) is not int
                    or not 0 <= start < end <= len(text)):
                raise ValueError(f"Line {line}: invalid entity type or offsets")
            spans.append((start, end))
            kinds_in_document.add(kind)
        ordered_spans = sorted(spans)
        if any(left[1] > right[0] for left, right in zip(
            ordered_spans, ordered_spans[1:], strict=False
        )):
            raise ValueError(f"Line {line}: overlapping entities")
        if not entities:
            if category != "NEGATIVE":
                raise ValueError(f"Line {line}: negative document category required")
            negatives += 1
        elif category == "NEGATIVE":
            raise ValueError(f"Line {line}: positive document marked negative")
        elif category not in kinds_in_document:
            raise ValueError(f"Line {line}: category is absent from entities")
        for kind in kinds_in_document:
            support[kind] += 1
    if any(count < minimum_per_kind for count in support.values()) or negatives < minimum_negatives:
        raise ValueError("Insufficient per-category or negative document support")
    return {"documents": len(rows), "negative_documents": negatives,
            "per_category_documents": support}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--minimum-per-kind", type=int, default=10)
    parser.add_argument("--minimum-negatives", type=int, default=20)
    args = parser.parse_args()
    rows = []
    for line, raw in enumerate(args.corpus.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError:
            raise SystemExit(f"Line {line}: invalid JSON") from None
    try:
        report = validate_rows(rows, args.minimum_per_kind, args.minimum_negatives)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
