"""Prototype geography: 3 regions, real district names, approximate centre coordinates.

Coordinates are approximate district centres (good enough for a map), not survey data.
"""

REGIONS: list[dict] = [
    {
        "code": "QQR",
        "name": "Qoraqalpog'iston Respublikasi",
        "lat": 42.46, "lon": 59.61,
        "perinatal": {"name": "Respublika perinatal markazi (Nukus)", "lat": 42.4619, "lon": 59.6166},
        "hb_shift": -8.0,  # synthetic: lower mean hemoglobin in this region
        "districts": [
            {"code": "NUK", "name": "Nukus tumani", "lat": 42.63, "lon": 59.63},
            {"code": "XOJ", "name": "Xo'jayli tumani", "lat": 42.40, "lon": 59.46},
            {"code": "CHI", "name": "Chimboy tumani", "lat": 42.94, "lon": 59.78},
            {"code": "BER", "name": "Beruniy tumani", "lat": 41.69, "lon": 60.75},
            {"code": "MOY", "name": "Mo'ynoq tumani", "lat": 43.77, "lon": 59.02},
        ],
    },
    {
        "code": "TSH",
        "name": "Toshkent shahri",
        "lat": 41.31, "lon": 69.28,
        "perinatal": {"name": "Respublika ixtisoslashtirilgan perinatal markazi", "lat": 41.300, "lon": 69.250},
        "hb_shift": 2.0,
        "districts": [
            {"code": "CHL", "name": "Chilonzor tumani", "lat": 41.275, "lon": 69.205},
            {"code": "YUN", "name": "Yunusobod tumani", "lat": 41.364, "lon": 69.287},
            {"code": "MUL", "name": "Mirzo Ulug'bek tumani", "lat": 41.338, "lon": 69.335},
            {"code": "YAK", "name": "Yakkasaroy tumani", "lat": 41.285, "lon": 69.265},
        ],
    },
    {
        "code": "FAR",
        "name": "Farg'ona viloyati",
        "lat": 40.38, "lon": 71.78,
        "perinatal": {"name": "Farg'ona viloyat perinatal markazi", "lat": 40.384, "lon": 71.786},
        "hb_shift": -3.0,
        "districts": [
            {"code": "FRG", "name": "Farg'ona tumani", "lat": 40.33, "lon": 71.72},
            {"code": "QOQ", "name": "Qo'qon shahri", "lat": 40.528, "lon": 70.943},
            {"code": "QUV", "name": "Quva tumani", "lat": 40.522, "lon": 72.070},
            {"code": "RIS", "name": "Rishton tumani", "lat": 40.357, "lon": 71.284},
        ],
    },
]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(a))
