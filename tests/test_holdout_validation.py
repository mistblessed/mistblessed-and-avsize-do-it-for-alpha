import pytest

from alfa_pii.domain import Kind
from tools.validate_holdout import validate_rows


def reviewed_rows():
    rows = []
    for index, kind in enumerate(Kind):
        rows.append({
            "id": f"case-{index}", "category": str(kind), "text": f"Value {index}",
            "entities": [{"kind": str(kind), "start": 6, "end": len(f"Value {index}")}],
        })
    rows.append({"id": "negative", "category": "NEGATIVE", "text": "No data", "entities": []})
    return rows


def test_validate_holdout_reports_support_without_echoing_text():
    report = validate_rows(reviewed_rows(), minimum_per_kind=1, minimum_negatives=1)

    assert report["documents"] == 18
    assert report["negative_documents"] == 1
    assert all(count == 1 for count in report["per_category_documents"].values())
    assert "Value" not in str(report)


@pytest.mark.parametrize("change", [
    lambda rows: rows[1].update(id=rows[0]["id"]),
    lambda rows: rows[1].update(text=rows[0]["text"]),
    lambda rows: rows[0]["entities"][0].update(end=999),
    lambda rows: rows[0]["entities"][0].update(kind="UNKNOWN"),
    lambda rows: rows[0].update(category="UNKNOWN"),
    lambda rows: rows[0].update(category=str(Kind.EMAIL)),
])
def test_validate_holdout_rejects_bad_annotations(change):
    rows = reviewed_rows()
    change(rows)

    with pytest.raises(ValueError):
        validate_rows(rows, minimum_per_kind=1, minimum_negatives=1)


def test_validate_holdout_enforces_per_type_and_negative_support():
    rows = reviewed_rows()

    with pytest.raises(ValueError, match="support"):
        validate_rows(rows, minimum_per_kind=10, minimum_negatives=20)
