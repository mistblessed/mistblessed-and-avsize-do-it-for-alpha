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
