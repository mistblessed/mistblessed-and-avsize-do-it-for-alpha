"""Regression tests for gaps found by the independent holdout.

These cases were discovered by running the independent holdout corpus
(tools/make_holdout.py) and are added here as development/regression data so the
detector is fixed against them without tuning directly against the holdout.
"""
import pytest

from alfa_pii.detection.engine import Detector, resolve


def spans(text, use_ner=False):
    return {(str(e.kind), e.start, e.end) for e in resolve(Detector(use_ner).detect(text))}


def value(text, kind):
    return [text[s:e] for k, s, e in spans(text) if k == kind]


# --- Recall gaps: labels/forms the detector missed ---

@pytest.mark.parametrize("text,expected", [
    ("День рождения 22/07/1988", "22/07/1988"),
    ("День рождения: 03.11.1992", "03.11.1992"),
])
def test_birth_date_day_label(text, expected):
    assert expected in value(text, "BIRTH_DATE")


@pytest.mark.parametrize("text,expected", [
    ("ВУ 78 02 234567", "78 02 234567"),
    ("ВУ: 77 04 456789", "77 04 456789"),
])
def test_driver_license_abbreviation_without_slash(text, expected):
    assert expected in value(text, "DRIVER_LICENSE")


@pytest.mark.parametrize("text,expected", [
    ("PIN-код карты: 9012", "9012"),
    ("PIN-код карты: 6789", "6789"),
])
def test_pin_latin_with_cyrillic_kod(text, expected):
    assert expected in value(text, "PIN")


@pytest.mark.parametrize("text,expected", [
    ("Паспорт выдан 12.05.2015", "12.05.2015"),
    ("Паспорт выдан 25.12.2012", "25.12.2012"),
])
def test_issue_date_pasport_vydan(text, expected):
    assert expected in value(text, "ISSUE_DATE")


# --- Precision gaps: public figures must not be flagged as PERSON ---

@pytest.mark.parametrize("text", [
    "Художник Иван Айвазовский известен морскими пейзажами.",
    "Композитор Петр Чайковский написал балет.",
    "Ученый Дмитрий Менделеев создал таблицу.",
    "Художник Илья Репин написал картину.",
    "Композитор Сергей Рахманинов написал концерт.",
    "Ученый Николай Лобачевский создал геометрию.",
])
@pytest.mark.ner
def test_public_figures_not_person(text):
    # NER flags these as PER; the public-context heuristic must suppress them.
    assert spans(text, use_ner=True) == set()


# --- Span boundaries: separators and abbreviations ---

@pytest.mark.parametrize("text,expected", [
    ("Место рождения — село Ивановка", "село Ивановка"),
    ("Место рождения — город Омск", "город Омск"),
])
def test_birth_place_dash_not_included(text, expected):
    assert expected in value(text, "BIRTH_PLACE")


@pytest.mark.parametrize("text,expected", [
    ("Гражданство — Республика Беларусь", "Республика Беларусь"),
    ("Гражданство — Российская Федерация", "Российская Федерация"),
])
def test_citizenship_dash_not_included(text, expected):
    assert expected in value(text, "CITIZENSHIP")


@pytest.mark.parametrize("text,expected", [
    ("Паспорт выдан ОМВД России по г. Москве", "ОМВД России по г. Москве"),
    ("Паспорт выдан: ОМВД России по г. Новосибирску", "ОМВД России по г. Новосибирску"),
])
def test_passport_issuer_abbreviation_not_truncated(text, expected):
    assert expected in value(text, "PASSPORT_ISSUER")


# --- Type conflicts ---

@pytest.mark.parametrize("text,expected", [
    ("Электронный адрес: info@company.org", "info@company.org"),
    ("Электронный адрес: admin@site.org", "admin@site.org"),
])
def test_email_not_address(text, expected):
    assert expected in value(text, "EMAIL")


def test_address_inflected_form_span():
    text = "Прописан по адресу: г. Омск, ул. Ленина, д. 25"
    assert "г. Омск, ул. Ленина, д. 25" in value(text, "ADDRESS")


def test_grazhdanin_with_name_is_person():
    text = "Гражданин: Лебедев Сергей"
    assert "Лебедев Сергей" in value(text, "PERSON")


# --- Free-text detection: realistic sentence structures without leading labels ---

def test_birth_date_followed_by_goda_rozhdeniya():
    text = "Иванов Иван Иванович, 12.01.1990 года рождения"
    assert "12.01.1990" in value(text, "BIRTH_DATE")


def test_issue_date_vydan_without_ot():
    text = "Паспорт 4512 987654, выдан 15.03.2015"
    assert "15.03.2015" in value(text, "ISSUE_DATE")


def test_address_without_dom_prefix():
    text = "Проживает: г. Москва, ул. Тверская, 7"
    assert "г. Москва, ул. Тверская, 7" in value(text, "ADDRESS")