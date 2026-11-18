"""ACTION CATALOG: the only actions the AI summary may recommend (by code).

Codes returned by the LLM are validated against this catalog; unknown codes are dropped.
This prevents hallucinated treatments. To be reviewed by a clinician.
"""

ACTIONS: dict[str, str] = {
    "A01": "Perinatal markazga shoshilinch yo'llash",
    "A02": "24 soat ichida arterial bosimni qayta o'lchash",
    "A03": "Siydikda oqsil tahlilini takrorlash",
    "A04": "Gemoglobin tahlilini 7 kun ichida takrorlash",
    "A05": "Temir preparatlari bo'yicha shifokor ko'rigi",
    "A06": "Homila holatini UTT/KTG bilan tekshirish",
    "A07": "Patronaj tashrifini 3 kun ichida o'tkazish",
    "A08": "Endokrinolog konsultatsiyasi",
    "A09": "Glyukoza tahlilini takrorlash (och qoringa)",
    "A10": "Akusher-ginekolog ko'rigiga 48 soat ichida yozish",
    "A11": "Xavfli belgilar haqida bemorga tushuntirish berish (qachon darhol murojaat qilish kerak)",
    "A12": "Homila harakatlarini sanash bo'yicha yo'riqnoma berish",
    "A13": "Tez tibbiy yordam chaqirish va tug'ruq bo'limiga yotqizish",
    "A14": "Harorat sababini aniqlash uchun shifokor ko'rigi",
    "A15": "Ovqatlanish va vazn nazorati bo'yicha maslahat",
    "A16": "Keyingi tashrif sanasini belgilash va eslatma yuborish",
    "A17": "Transport va perinatal markazga yetib borish rejasini tuzish",
    "A18": "Terapevt yoki tegishli mutaxassis konsultatsiyasi (surunkali kasallik)",
    "A19": "Rezus-antitelalar tahlilini tekshirish",
    "A20": "Tug'ruq rejasini perinatal markaz bilan kelishish",
    # children 0-12 months (task 08)
    "A21": "Bolani shoshilinch ravishda bolalar shifoxonasiga yo'llash",
    "A22": "Pediatr ko'rigiga 24 soat ichida yozish",
    "A23": "Emizish va ovqatlantirish bo'yicha onaga maslahat",
    "A24": "Vaznni 7-14 kun ichida qayta o'lchash va o'sish grafigini kuzatish",
    "A25": "Kechikkan emlashlar uchun emlash xonasiga yo'llash",
    "A26": "Patronaj hamshirasining bolani uyda ko'rishi (3 kun ichida)",
    "A27": "Suvsizlanish belgilarini baholash va onaga suyuqlik berish bo'yicha tushuntirish",
    "A28": "Onaga bolaning xavfli belgilari haqida tushuntirish (qachon darhol murojaat qilish kerak)",
}

# Deterministic rule/trend -> action mapping used by the template fallback.
RULE_ACTIONS: dict[str, list[str]] = {
    "R01": ["A13", "A01"], "R02": ["A01", "A03", "A11"], "R03": ["A01", "A05"], "R04": ["A13"],
    "R05": ["A13", "A01"], "R06": ["A01", "A06"], "R07": ["A06", "A01"], "R08": ["A14"],
    "R09": ["A13"], "R10": ["A08", "A01"],
    "Y01": ["A10"], "Y02": ["A20"], "Y03": ["A20"], "Y04": ["A10", "A20"], "Y05": ["A02", "A03"],
    "Y06": ["A04", "A05"], "Y07": ["A09", "A08"], "Y08": ["A15"], "Y09": ["A06", "A20"], "Y10": ["A18"],
    "Y11": ["A10"], "Y12": ["A19"], "Y13": ["A07", "A16"], "Y14": ["A01"], "Y15": ["A17"],
    "T01": ["A04", "A05"], "T02": ["A02", "A03"], "T03": ["A02", "A03", "A07"], "T04": ["A06"],
    "T05": ["A10"],
    "P01": ["A02", "A03", "A10"], "P02": ["A04", "A05"], "P03": ["A02", "A03", "A07"], "P04": ["A06", "A10"],
    "P05": ["A10"],
    # newborn (day 0-28) and infant (0-12 months)
    **{c: ["A21", "A28"] for c in ("N01", "N02", "N03", "N04", "N05", "N06", "N07", "N08")},
    "N09": ["A22", "A24"], "N10": ["A22", "A24"], "N11": ["A22"], "N12": ["A22"], "N13": ["A26"],
    **{c: ["A21", "A28"] for c in ("I01", "I03", "I04", "I05", "I06", "I07")},
    "I02": ["A21", "A27"], "I08": ["A21", "A27"], "I09": ["A21", "A27"],
    "I10": ["A24", "A23", "A22"], "I11": ["A25"], "I12": ["A22"], "I13": ["A26"], "I14": ["A23"],
    "G01": ["A24", "A23", "A22"], "G02": ["A24", "A23", "A22"],
}


def validate_codes(codes: list[str]) -> list[str]:
    """Keep only catalog codes, de-duplicated, in order."""
    seen: list[str] = []
    for c in codes:
        c = str(c).strip().upper()
        if c in ACTIONS and c not in seen:
            seen.append(c)
    return seen
