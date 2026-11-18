"""Output safety checks for AI text shown to clinicians (doctor bullets).

Decision support, not diagnosis: no diagnosis wording. Privacy: no PINFL / phone-like digit runs (the LLM never
receives them, so a match means the model invented or leaked something). Any problem -> the attempt is rejected
and the chain moves on (plain retry -> template "Shablon").
"""
import re

BULLET_COUNT = 3
BULLET_MAX_CHARS = 160

# Diagnosis wording in Uzbek (Latin + Cyrillic), Russian and English. Lower-case substring match.
DIAGNOSIS_WORDS = ("tashxis", "ташхис", "diagnoz", "диагноз", "diagnosis", "diagnosed")

_DIGIT_RUN = re.compile(r"\+?\d[\d\s\-()]{7,}\d")  # 9+ digits with optional separators: phone / PINFL-like


def pii_problems(text: str) -> list[str]:
    problems = []
    for m in _DIGIT_RUN.finditer(text):
        if sum(ch.isdigit() for ch in m.group()) >= 9:
            problems.append("raqamlar ketma-ketligi (telefon/JShShIR shakli)")
            break
    if "+998" in text:
        problems.append("telefon raqami")
    return problems


def diagnosis_problems(text: str) -> list[str]:
    low = text.lower()
    return [f"tashxis so'zi: {w}" for w in DIAGNOSIS_WORDS if w in low]


def validate_bullets(bullets: list[str]) -> list[str]:
    """Exactly BULLET_COUNT non-empty bullets, each <= BULLET_MAX_CHARS, no PII, no diagnosis words."""
    cleaned = [b.strip().lstrip("•-* ").strip() for b in bullets]
    if len(cleaned) != BULLET_COUNT:
        raise ValueError(f"doctor_bullets_uz: exactly {BULLET_COUNT} bullets required, got {len(cleaned)}")
    for i, b in enumerate(cleaned, 1):
        if not b:
            raise ValueError(f"doctor_bullets_uz[{i}] is empty")
        if len(b) > BULLET_MAX_CHARS:
            raise ValueError(f"doctor_bullets_uz[{i}] longer than {BULLET_MAX_CHARS} chars")
        problems = pii_problems(b) + diagnosis_problems(b)
        if problems:
            raise ValueError(f"doctor_bullets_uz[{i}] rejected: {', '.join(problems)}")
    return cleaned


def clip(text: str, limit: int = BULLET_MAX_CHARS) -> str:
    """Shorten to `limit` chars on a word boundary (template bullets are built from variable-length hit texts)."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:—-")
    return cut + "…"
