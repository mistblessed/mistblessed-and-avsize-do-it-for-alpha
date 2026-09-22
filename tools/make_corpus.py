"""Generate synthetic DEVELOPMENT fixtures. This is not an independent holdout."""
import argparse
import json
from pathlib import Path

SAMPLES = [
    ("PERSON", "ФИО", "Сидоров Алексей Петрович"),
    ("BIRTH_DATE", "Дата рождения", "23 февраля 1987 года"),
    ("BIRTH_PLACE", "Место рождения", "город Самара"),
    ("PASSPORT", "Паспорт", "4510 654321"),
    ("CITIZENSHIP", "Гражданство", "Российская Федерация"),
    ("PASSPORT_ISSUER", "Кем выдан", "ОМВД России по району Центральный"),
    ("DEPARTMENT_CODE", "Код подразделения", "630-001"),
    ("ISSUE_DATE", "Дата выдачи паспорта", "2010.23.02"),
    ("DRIVER_LICENSE", "Водительское удостоверение", "63 10 654321"),
    ("ADDRESS", "Адрес клиента", "г. Самара, ул. Лесная, д. 12, кв. 3"),
    ("EMAIL", "Email", "synthetic.person@example.org"),
    ("PHONE", "Телефон", "+7 (999) 234-56-78"),
    ("INN", "ИНН", "630123456789"),
    ("CARD", "Номер карты", "4111 1111 1111 1111"),
    ("CVV", "CVV", "654"),
    ("PIN", "Пин-код карты", "7654"),
    ("CARDHOLDER", "Имя держателя карты", "ALEXEY SIDOROV"),
]
NEGATIVES = ["Поэт Александр Пушкин написал стихотворение.",
             "Адрес отделения банка: г. Самара, ул. Лесная, д. 12;",
             "Пин-код карты нельзя сообщать посторонним.",
             "Встреча 23.02.2025, номер заказа 654, сумма 7654 рублей."]


def generate() -> list[dict]:
    rows = []
    for kind, label, value in SAMPLES:
        for i in range(12):
            prefix = ["", "Анкета. ", "Сведения:\n", "\t"][i % 4]
            transform = [str, str.lower, str.upper][i // 4]
            lead = transform(prefix + label + ": ")
            item = transform(value)
            rows.append({"id": f"dev-{kind}-{i}", "category": kind,
                         "text": lead + item + ";", "entities": [{"kind": kind, "start": len(lead), "end": len(lead) + len(item)}]})
        for i in range(8):
            text = NEGATIVES[i % 4]
            rows.append({"id": f"dev-{kind}-negative-{i}", "category": kind,
                         "text": text if i < 4 else text.upper(), "entities": []})
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in generate()) + "\n", encoding="utf-8")
    print("Generated 340 development examples. Repeated negative templates are not independent evidence.")

