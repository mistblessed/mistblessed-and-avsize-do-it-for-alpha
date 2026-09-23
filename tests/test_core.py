import pytest
from hypothesis import given
from hypothesis import strategies as st

from alfa_pii.detection.engine import Detector
from alfa_pii.domain import Entity, Kind
from alfa_pii.transformation.masking import mask, restore

CASES = [
    (Kind.PERSON, "Клиент: Иванов Иван Иванович", "Иванов Иван Иванович"),
    (Kind.BIRTH_DATE, "Дата рождения: 12 января 1990 года", "12 января 1990 года"),
    (Kind.BIRTH_PLACE, "Место рождения: город Тверь;", "город Тверь"),
    (Kind.PASSPORT, "Паспорт: серия 4509 номер 123456", "4509 номер 123456"),
    (Kind.CITIZENSHIP, "Гражданство: Российская Федерация;", "Российская Федерация"),
    (Kind.PASSPORT_ISSUER, "Кем выдан: ОМВД России по району Тверской;", "ОМВД России по району Тверской"),
    (Kind.DEPARTMENT_CODE, "Код подразделения: 770-001", "770-001"),
    (Kind.ISSUE_DATE, "Дата выдачи паспорта: 2001.25.12", "2001.25.12"),
    (Kind.DRIVER_LICENSE, "Водительское удостоверение: 77 01 123456", "77 01 123456"),
    (Kind.ADDRESS, "Адрес клиента: г. Тверь, ул. Мира, д. 5, кв. 8;", "г. Тверь, ул. Мира, д. 5, кв. 8"),
    (Kind.EMAIL, "Почта test.person@example.org", "test.person@example.org"),
    (Kind.PHONE, "Телефон: +7 (999) 123-45-67", "+7 (999) 123-45-67"),
    (Kind.INN, "ИНН: 770123456789", "770123456789"),
    (Kind.CARD, "Номер карты: 4111 1111 1111 1111", "4111 1111 1111 1111"),
    (Kind.CVV, "CVV: 321", "321"),
    (Kind.PIN, "Пин-код карты: 4321", "4321"),
    (Kind.CARDHOLDER, "Имя держателя карты: IVAN IVANOV", "IVAN IVANOV"),
]


@pytest.mark.parametrize("kind,text,value", CASES)
@pytest.mark.parametrize("case", [str, str.lower, str.upper])
def test_required_category_offsets(kind, text, value, case):
    text, value = case(text), case(value)
    found = Detector(use_ner=False).detect(text)
    assert any(e.kind == kind and text[e.start:e.end] == value for e in found)


@pytest.mark.parametrize("text", [
    "Поэт Александр Пушкин написал стихотворение.",
    "Адрес отделения банка: г. Тверь, ул. Мира, д. 5;",
    "Встреча 12.01.2025, номер заказа 321, сумма 4321 рублей.",
    "Пин-код карты нельзя сообщать посторонним.",
])
def test_public_and_non_personal_text(text):
    assert Detector(use_ner=False).detect(text) == []


@pytest.mark.parametrize("mode", ["layout_mask", "typed_tokens"])
def test_exact_roundtrip_and_full_replacement(mode):
    text = "🙂\tИванов  Иван\r\nemail: one@example.org!"
    start = text.index("Иванов")
    email = text.index("one@")
    entities = [Entity(Kind.PERSON, start, start + len("Иванов  Иван")),
                Entity(Kind.EMAIL, email, email + len("one@example.org"))]
    result = mask(text, entities, mode)
    assert "Иванов" not in result.text
    assert "one@example.org" not in result.text
    assert restore(result.text, result) == text
    if mode == "layout_mask":
        assert len(result.text) == len(text)
        assert "\r\n" in result.text


@given(st.text(min_size=1).filter(lambda t: any(c.isalnum() for c in t)))
def test_arbitrary_unicode_roundtrip(text):
    for mode in ["layout_mask", "typed_tokens"]:
        result = mask(text, [Entity(Kind.PERSON, 0, len(text))], mode)
        assert result.text != text
        assert restore(result.text, result) == text


@given(st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=5))
def test_multiple_entities_roundtrip(parts):
    text = "".join(parts)
    # Build non-overlapping entities covering every other part.
    entities = []
    cursor = 0
    for i, part in enumerate(parts):
        if i % 2 == 0 and part:
            entities.append(Entity(Kind.PERSON, cursor, cursor + len(part)))
        cursor += len(part)
    if not entities:
        return
    for mode in ["layout_mask", "typed_tokens"]:
        result = mask(text, entities, mode)
        assert restore(result.text, result) == text


@given(st.text(min_size=1, max_size=50).filter(lambda t: any(c.isalnum() for c in t)))
def test_layout_mask_preserves_length_and_non_alnum(text):
    result = mask(text, [Entity(Kind.PERSON, 0, len(text))], "layout_mask")
    assert len(result.text) == len(text)
    for a, b in zip(text, result.text, strict=True):
        if not a.isalnum():
            assert a == b


@given(
    st.text(min_size=2, max_size=30).filter(
        lambda t: any(c.isalnum() for c in t) and t not in f"⟦{Kind.PERSON}:⟧"
    )
)
def test_typed_tokens_never_contain_original(text):
    result = mask(text, [Entity(Kind.PERSON, 0, len(text))], "typed_tokens")
    assert text not in result.text
    assert all(orig not in result.text for orig in result.tokens.values())


def test_typed_tokens_retry_when_random_id_contains_original(monkeypatch):
    generated = iter(["0" * 24, "abcdef123456789abcdef123"])
    monkeypatch.setattr("alfa_pii.transformation.masking.secrets.token_hex", lambda _: next(generated))

    result = mask("00", [Entity(Kind.CVV, 0, 2)], "typed_tokens")

    assert "00" not in result.text


def test_tokens_stable_inside_request_and_scoped_between_requests():
    text = "Иван Иван"
    spans = [Entity(Kind.PERSON, 0, 4), Entity(Kind.PERSON, 5, 9)]
    first, second = mask(text, spans, "typed_tokens"), mask(text, spans, "typed_tokens")
    assert len(first.tokens) == 1
    assert first.text.split()[0] == first.text.split()[1]
    assert first.text != second.text
    assert restore(first.text, second) == first.text


@pytest.mark.parametrize("kind,text,value", [
    (Kind.PERSON, "ФИО: Иванов И. И.;", "Иванов И. И."),
    (Kind.PERSON, "Клиент: И. И. Иванов;", "И. И. Иванов"),
    (Kind.ADDRESS, "Доставка: г. Тверь, ул. Мира, д. 5, кв. 8;", "г. Тверь, ул. Мира, д. 5, кв. 8"),
    (Kind.ADDRESS, "ул. Лесная, д. 12, корп. 2, кв. 3", "ул. Лесная, д. 12, корп. 2, кв. 3"),
])
def test_common_unstructured_forms(kind, text, value):
    assert any(e.kind == kind and text[e.start:e.end] == value for e in Detector(False).detect(text))
