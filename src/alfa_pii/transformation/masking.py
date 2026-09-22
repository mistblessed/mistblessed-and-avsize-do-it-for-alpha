"""Preserve untouched text; token restoration never recursively expands replacements."""
import re
import secrets

from alfa_pii.domain import Entity, MaskResult, ServiceError


def mask(text: str, entities: list[Entity], mode: str) -> MaskResult:
    if mode not in {"layout_mask", "typed_tokens"}:
        raise ValueError("Unsupported mask mode")
    result = MaskResult("")
    parts: list[str] = []
    cursor = 0
    identities: dict[tuple[str, str], str] = {}
    for e in sorted(entities, key=lambda e: e.start):
        if not cursor <= e.start < e.end <= len(text):
            raise ValueError("Invalid or overlapping entity offsets")
        parts.append(text[cursor:e.start])
        original = text[e.start:e.end]
        if mode == "layout_mask":
            replacement = "".join("*" if c.isalnum() else c for c in original)
            result.replacements.append({"start": e.start, "end": e.end, "original": original})
        else:
            identity = (str(e.kind), original)
            if identity not in identities:
                token = f"⟦{e.kind}:{secrets.token_hex(12)}⟧"
                while token in text:
                    token = f"⟦{e.kind}:{secrets.token_hex(12)}⟧"
                identities[identity] = token
                result.tokens[token] = original
            replacement = identities[identity]
        parts.append(replacement)
        cursor = e.end
        result.types.append(str(e.kind))
    parts.append(text[cursor:])
    result.text = "".join(parts)
    result.types = sorted(set(result.types))
    return result


def restore(text: str, mapping: MaskResult) -> str:
    if mapping.tokens:
        pattern = re.compile(r"⟦[A-Z_]+:[0-9a-f]{24}⟧")
        return pattern.sub(lambda m: mapping.tokens.get(m.group(), m.group()), text)
    if mapping.replacements:
        if text != mapping.text:
            raise ServiceError(409, "layout_mask_changed")
        parts: list[str] = []
        cursor = 0
        for item in mapping.replacements:
            start, end = int(item["start"]), int(item["end"])
            parts.extend((text[cursor:start], str(item["original"])))
            cursor = end
        parts.append(text[cursor:])
        return "".join(parts)
    return text

