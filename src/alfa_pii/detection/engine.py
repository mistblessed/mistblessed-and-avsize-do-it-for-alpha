"""Bounded local rules and Russian NER; source text is never normalized."""
from bisect import bisect_right
from typing import Any

import regex as re

from alfa_pii.domain import Entity, Kind, ServiceError

WORD = r"[А-ЯЁA-Zа-яёa-z][А-ЯЁA-Zа-яёa-z'’\-]{1,39}"
NAME = rf"{WORD}(?:[ \t]+{WORD}){{1,2}}"
INITIALS = r"(?:[А-ЯЁA-Z]\.[ \t]*){1,2}"
PERSON_NAME = rf"(?:{WORD}[ \t]+{INITIALS}|{INITIALS}{WORD}|{NAME})"
STREET_ADDRESS = (r"(?<!\w)(?P<value>(?:г(?:ород)?\.?\s+[^,;\n]{1,60},\s*)?"
                  r"(?:ул(?:ица)?|проспект|пр-т|пер(?:еулок)?|шоссе|наб(?:ережная)?)\.?\s+"
                  r"[^,;\n]{1,80},?\s+(?:д(?:ом)?\.?\s*)?\d{1,5}[а-яёa-z]?"
                  r"(?:\s*,?\s*(?:корп(?:ус)?\.?|к\.|стр(?:оение)?\.?)\s*\d{1,5}[а-яёa-z]?)?"
                  r"(?:\s*,?\s*кв(?:артира)?\.?\s*\d{1,5}[а-яёa-z]?)?)(?!\w)")
DATE = (r"(?:\d{1,4}[./-]\d{1,2}[./-]\d{1,4}|\d{1,2}\s+"
        r"(?:январ[яь]|феврал[яь]|март[а]?|апрел[яь]|ма[йя]|июн[яь]|июл[яь]|"
        r"август[а]?|сентябр[яь]|октябр[яь]|ноябр[яь]|декабр[яь])\s+\d{4}"
        r"(?:\s+года|\s+г\.)?)")
LABELS = (r"(?:дата\s+(?:рождения|выдачи)|место\s+рождения|паспорт|гражданство|"
          r"кем\s+выдан|код\s+подразделения|водительское\s+удостоверение|адрес|"
          r"email|e-mail|телефон|инн|cvv|cvc|pin|пин|имя\s+держателя|фио)\s*:")
# Abbreviations whose trailing period is not a sentence boundary (г., ул., д., ...).
ABBREV = r"(?:г|ул|д|пр|кв|корп|стр|обл|пос|дер|с|р-н)"
FIELD = rf"[^;\n!?]{{1,250}}?(?=\s*{LABELS}|[;\n!?]|(?<!{ABBREV})\.(?:\s|$)|$)"
PERSONAL = re.compile(r"клиент|пациент|за[её]мщик|заявитель|мой|мо[яё]|прожива|регистрац|фио", re.I)
PUBLIC = re.compile(r"поэт|писател|памятник|художник|композитор|ученый|учёный|скульптор|архитектор|отделени[ея]\s+банка|офис\s+банка|филиал\s+банка", re.I)
TOKEN = re.compile(r"⟦[A-Z_]+:[0-9a-f]{24}⟧")


def labeled(label: str, value: str) -> str:
    return rf"(?<!\w)(?:{label})\s*[:=№\-—]?\s*(?P<value>(?![\s:=\-—]){value})(?!\w)"


SPECS: list[tuple[Kind, str]] = [
    (Kind.PERSON, labeled(r"ф\.?\s*и\.?\s*о\.?|клиент(?:а|у)?|за[её]мщик|заявитель|гражданин|гражданка", PERSON_NAME)),
    (Kind.BIRTH_DATE, labeled(r"дата\s+рождения|день\s+рождения|д\.?\s*р\.?|родил(?:ся|ась)", DATE)),
    (Kind.BIRTH_DATE, rf"(?<!\d)(?P<value>{DATE})\s+(?:года\s+рождения|г\.?\s*р\.?)(?!\w)"),
    (Kind.BIRTH_DATE, r"(?<!\d)(?P<value>(?:19|20)\d{2})\s+(?:года\s+рождения|г\.?\s*р\.?)(?!\w)"),
    (Kind.BIRTH_PLACE, labeled(r"место\s+рождения|родил(?:ся|ась)\s+в", FIELD)),
    (Kind.PASSPORT, labeled(r"паспорт(?:\s+РФ)?(?:\s+серия)?|серия", r"\d{2}\s?\d{2}\s*(?:номер|№)?\s*\d{6}")),
    (Kind.PASSPORT, r"(?<!\d)(?P<value>\d{4}[ \t]+\d{6})(?!\d)"),
    (Kind.CITIZENSHIP, labeled(r"гражданство|гражданин(?!\s*[:=№\-—])|гражданка(?!\s*[:=№\-—])", FIELD)),
    (Kind.PASSPORT_ISSUER, labeled(r"кем\s+выдан|орган(?:,?\s+выдавший\s+паспорт|\s+выдачи)|паспорт\s+выдан", FIELD)),
    (Kind.DEPARTMENT_CODE, labeled(r"код\s+подразделения", r"\d{3}[ \t-]?\d{3}")),
    (Kind.ISSUE_DATE, labeled(r"дата\s+выдачи(?:\s+паспорта)?|паспорт\s+выдан|выдан(?:\s+от)?", DATE)),
    (Kind.DRIVER_LICENSE, labeled(r"водительское\s+удостоверение|в\s*/?\s*у", r"\d{2}\s?[\dА-ЯЁ]{2}\s?\d{6}")),
    (Kind.ADDRESS, labeled(r"(?<!электронный\s)адрес(?:у|а|ом|е)?(?:\s+(?:клиента|регистрации|проживания|доставки))?|проживает\s+(?:по\s+адресу|в)|зарегистрирован[а]?\s+(?:по\s+адресу|в)|прописан[а]?\s+(?:по\s+адресу|в)", rf"[^;\n!?]{{1,250}}?(?=\s*{LABELS}|[;\n!?]|$)")),
    (Kind.ADDRESS, labeled(r"страна|город|насел[её]нный\s+пункт|улица|дом|квартира|почтовый\s+индекс", r"[^;,\n!?]{1,100}")),
    (Kind.ADDRESS, STREET_ADDRESS),
    (Kind.EMAIL, r"(?<![\w.+-])(?P<value>[\w.!#$%&'*+/=?^`{|}~\-]+@[\w-]+(?:\.[\w-]+)+)(?![\w-])"),
    (Kind.PHONE, r"(?<!\w)(?P<value>(?:\+7|8)[ \t-]*\(?\d{3}\)?[ \t-]*\d{3}[ \t-]*\d{2}[ \t-]*\d{2})(?!\d)"),
    (Kind.PHONE, labeled(r"телефон|тел\.?|мобильный", r"\+?\d[\d() \t-]{8,22}\d")),
    (Kind.INN, labeled(r"инн", r"(?:\d{12}|\d{10})")),
    (Kind.CARD, labeled(r"(?:номер\s+)?(?:банковской\s+)?карт[аы]|pan", r"\d(?:[ \t-]?\d){12,18}")),
    (Kind.CVV, labeled(r"cvv2?|cvc2?|код\s+безопасности(?:\s+карты)?", r"\d{3,4}")),
    (Kind.PIN, labeled(r"пин(?:[ \t-]*код)?(?:\s+карты)?|pin(?:[ \t-]*(?:code|код))?(?:\s+карты)?", r"\d{4,6}")),
    (Kind.CARDHOLDER, labeled(r"имя\s+держателя(?:\s+карты)?|держатель(?:\s+карты)?|cardholder", NAME)),
]
RULES = [(kind, re.compile(pattern, re.I)) for kind, pattern in SPECS]
CARD = re.compile(r"(?<!\d)(?P<value>\d(?:[ -]?\d){12,18})(?!\d)")
INN = re.compile(r"(?<!\d)(?P<value>\d{12}|\d{10})(?!\d)")


def luhn(value: str) -> bool:
    digits = [int(c) for c in value if c.isdigit() and c.isascii()]
    if not 13 <= len(digits) <= 19 or len(set(digits)) < 2:
        return False
    total = sum((d * 2 - 9 if d * 2 > 9 else d * 2) if i % 2 else d
                for i, d in enumerate(reversed(digits)))
    return total % 10 == 0


def valid_inn(value: str) -> bool:
    if not value.isascii() or not value.isdigit() or len(set(value)) < 2:
        return False
    d = list(map(int, value))
    def checksum(weights: list[int]) -> int:
        return sum(a * b for a, b in zip(d, weights, strict=False)) % 11 % 10
    if len(d) == 10:
        return checksum([2, 4, 10, 3, 5, 9, 4, 6, 8]) == d[9]
    if len(d) == 12:
        return (checksum([7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == d[10]
                and checksum([3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == d[11])
    return False


def is_public(text: str, start: int) -> bool:
    prefix = text[max(0, start - 100):start]
    public = list(PUBLIC.finditer(prefix))
    personal = list(PERSONAL.finditer(prefix))
    return bool(public and (not personal or public[-1].start() > personal[-1].start()))


class Detector:
    def __init__(self, use_ner: bool = True, extra_rules: list[dict[str, str]] | None = None) -> None:
        self.rules = RULES + [(r["kind"], re.compile(r["pattern"], re.I)) for r in extra_rules or []]
        self.segmenter: Any = None
        self.ner: Any = None
        if use_ner:
            from natasha import NewsEmbedding, NewsNERTagger, Segmenter
            self.segmenter = Segmenter()
            self.ner = NewsNERTagger(NewsEmbedding())

    def detect(self, text: str) -> list[Entity]:
        found: dict[tuple[str, int, int], Entity] = {}
        step, overlap = 4096, 512
        for base in range(0, len(text), step):
            left, right = max(0, base - overlap), min(len(text), base + step + overlap)
            for entity in self._block(text[left:right]):
                if (left and entity.start == 0) or (right < len(text) and entity.end == right - left):
                    continue
                e = Entity(entity.kind, entity.start + left, entity.end + left,
                           entity.confidence, entity.source, entity.components)
                found[(str(e.kind), e.start, e.end)] = e
        return sorted(found.values(), key=lambda e: (e.start, e.end, str(e.kind)))

    def _block(self, text: str) -> list[Entity]:
        result: list[Entity] = []
        def add(kind: Kind | str, start: int, end: int, source: str = "rule") -> None:
            while end > start and text[end - 1].isspace():
                end -= 1
            if start >= end:
                return
            if kind == Kind.ADDRESS and PUBLIC.match(text[start:end]):
                return
            if kind in {Kind.PERSON, Kind.ADDRESS} and is_public(text, start):
                return
            result.append(Entity(kind, start, end, source=source))
        try:
            for kind, pattern in self.rules:
                for match in pattern.finditer(text, timeout=0.05):
                    add(kind, *match.span("value"))
            for match in CARD.finditer(text, timeout=0.05):
                if luhn(match["value"]):
                    add(Kind.CARD, match.start("value"), match.end("value"), "checksum")
            for match in INN.finditer(text, timeout=0.05):
                if valid_inn(match["value"]):
                    add(Kind.INN, match.start("value"), match.end("value"), "checksum")
        except TimeoutError as exc:
            raise ServiceError(503, "detector_timeout") from exc
        # NER is the dominant CPU cost. When rules already located a PERSON or
        # ADDRESS in this chunk, NER is redundant for the common structured case;
        # skip it to keep throughput high. NER still runs when rules miss both.
        if self.ner is not None and not any(e.kind in {Kind.PERSON, Kind.ADDRESS} for e in result):
            from natasha import Doc
            doc = Doc(text)
            doc.segment(self.segmenter)
            doc.tag_ner(self.ner)
            for span in doc.spans:
                if span.type == "PER":
                    if (text[span.start:span.stop].casefold() in {"анкета", "сведения", "заявление", "договор", "резюме"}
                            and not text[:span.start].strip()
                            and text[span.stop:span.stop + 1] in {".", ":", "\n"}):
                        continue
                    add(Kind.PERSON, span.start, span.stop, "ner")
                elif span.type == "LOC" and PERSONAL.search(text[max(0, span.start - 80):span.start]):
                    add(Kind.ADDRESS, span.start, span.stop, "ner")
        return result


def resolve(entities: list[Entity]) -> list[Entity]:
    priority: dict[str, int] = {Kind.CARDHOLDER: 10, Kind.DRIVER_LICENSE: 9, Kind.PASSPORT: 8,
                Kind.ISSUE_DATE: 8, Kind.BIRTH_PLACE: 7, Kind.CITIZENSHIP: 7, Kind.PASSPORT_ISSUER: 7,
                Kind.BIRTH_DATE: 7, Kind.ADDRESS: 6}
    groups: list[list[Entity]] = []
    boundary = -1
    for e in sorted(entities, key=lambda e: (e.start, e.end)):
        if e.start >= boundary:
            groups.append([])
        groups[-1].append(e)
        boundary = max(boundary, e.end)
    output: list[Entity] = []
    for group in groups:
        selected: list[Entity] = []
        starts: list[int] = []
        for e in sorted(group, key=lambda e: (e.source != "ner", priority.get(e.kind, 5), e.end - e.start), reverse=True):
            pos = bisect_right(starts, e.start)
            if (pos and selected[pos - 1].end > e.start) or (pos < len(selected) and selected[pos].start < e.end):
                continue
            starts.insert(pos, e.start)
            selected.insert(pos, e)
        output.extend(selected)
    return output
