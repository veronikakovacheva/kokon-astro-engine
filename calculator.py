from datetime import date as Date
import swisseph as swe
from kerykeion.astrological_subject_factory import AstrologicalSubjectFactory
from kerykeion.aspects import AspectsFactory

# ── Sign mappings ─────────────────────────────────────────────────────────────

SIGNS_FULL = {
    "Ari": "Aries",       "Tau": "Taurus",      "Gem": "Gemini",
    "Can": "Cancer",      "Leo": "Leo",          "Vir": "Virgo",
    "Lib": "Libra",       "Sco": "Scorpio",      "Sag": "Sagittarius",
    "Cap": "Capricorn",   "Aqu": "Aquarius",     "Pis": "Pisces",
}

SIGNS_ORDER = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]
SIGN_TO_IDX = {s: i for i, s in enumerate(SIGNS_ORDER)}

HOUSE_WORDS = {
    "First": 1, "Second": 2,  "Third": 3,  "Fourth": 4,
    "Fifth": 5, "Sixth": 6,   "Seventh": 7, "Eighth": 8,
    "Ninth": 9, "Tenth": 10,  "Eleventh": 11, "Twelfth": 12,
}

HOUSE_ATTRS = [
    "first_house", "second_house", "third_house",  "fourth_house",
    "fifth_house", "sixth_house",  "seventh_house", "eighth_house",
    "ninth_house", "tenth_house",  "eleventh_house", "twelfth_house",
]

PLANET_ATTRS = [
    ("Sun",        "sun"),        ("Moon",       "moon"),
    ("Mercury",    "mercury"),    ("Venus",      "venus"),
    ("Mars",       "mars"),       ("Jupiter",    "jupiter"),
    ("Saturn",     "saturn"),     ("Uranus",     "uranus"),
    ("Neptune",    "neptune"),    ("Pluto",      "pluto"),
    ("Chiron",     "chiron"),     ("Mean_Lilith","mean_lilith"),
    ("Mean_Node",  "mean_node"),
]

# ── Aspect definitions ────────────────────────────────────────────────────────

ASPECT_ANGLES = [
    ("conjunction",  0,   8),
    ("opposition",   180, 8),
    ("trine",        120, 7),
    ("square",       90,  7),
    ("sextile",      60,  5),
    ("quincunx",     150, 3),
    ("semi-square",  45,  2),
    ("semi-sextile", 30,  2),
]

# Significance 1-5 for transit outer/inner planets
SIGNIFICANCE = {
    "Sun": 3, "Moon": 1, "Mercury": 2, "Venus": 2, "Mars": 2,
    "Jupiter": 3, "Saturn": 4, "Uranus": 4, "Neptune": 5, "Pluto": 5,
    "Chiron": 2, "Mean_Lilith": 2, "Mean_Node": 2,
}

# Synastry scoring: positive = harmonious, negative = tense
ASPECT_SCORE = {
    "conjunction": 3, "trine": 2, "sextile": 1,
    "opposition": -2, "square": -2, "quincunx": -1,
    "semi-square": -1, "semi-sextile": 0,
}

# Higher weight for personal planets
PLANET_WEIGHT = {
    "Sun": 3, "Moon": 3, "Venus": 3, "Mars": 3,
    "Mercury": 2, "Jupiter": 2, "Saturn": 2,
    "Uranus": 1, "Neptune": 1, "Pluto": 1,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _field(obj, key, default=None):
    """Access a field from either a dict or an object (Pydantic model)."""
    try:
        return obj[key] if isinstance(obj, dict) else getattr(obj, key, default)
    except (KeyError, TypeError):
        return default


def _sign_full(sign: str) -> str:
    return SIGNS_FULL.get(sign, sign)


def _house_num(house_str: str) -> int:
    word = str(house_str).replace("_House", "").replace("_house", "").strip()
    return HOUSE_WORDS.get(word, 0)


def _abs_deg(sign: str, degree: float) -> float:
    """Convert sign + within-sign degree to absolute ecliptic degree (0-360)."""
    return SIGN_TO_IDX.get(sign, 0) * 30.0 + degree


def _angle_diff(a: float, b: float) -> float:
    diff = abs(a - b) % 360
    return 360 - diff if diff > 180 else diff


def _find_aspect(deg1: float, deg2: float):
    diff = _angle_diff(deg1, deg2)
    for name, angle, orb in ASPECT_ANGLES:
        if abs(diff - angle) <= orb:
            return name, round(abs(diff - angle), 2)
    return None, None


def _make_subject(name, year, month, day, hour, minute, lat, lng, tz_str, city=""):
    return AstrologicalSubjectFactory.from_birth_data(
        name=name, year=year, month=month, day=day,
        hour=hour, minute=minute,
        lat=lat, lng=lng, tz_str=tz_str,
        city=city or "Unknown", nation="",
    )


def _planet_house(subj, abs_deg: float) -> int:
    cusps = []
    for attr in HOUSE_ATTRS:
        h = getattr(subj, attr, None)
        if h is None:
            continue
        cusps.append(_abs_deg(_sign_full(_field(h, "sign", "")), float(_field(h, "position", 0))))
    for i in range(12):
        start = cusps[i]
        end = cusps[(i + 1) % 12]
        if start <= end:
            if start <= abs_deg < end:
                return i + 1
        else:
            if abs_deg >= start or abs_deg < end:
                return i + 1
    return 1


def _selena_planet(subj) -> dict | None:
    try:
        jd = float(subj.julian_day)
        result, _ = swe.calc_ut(jd, swe.INTP_APOG)
        abs_deg = result[0]
        sign = SIGNS_ORDER[int(abs_deg // 30)]
        within = round(abs_deg % 30, 4)
        return {
            "name": "Selena",
            "sign": sign,
            "degree": within,
            "house": _planet_house(subj, abs_deg),
            "retrograde": False,
        }
    except Exception:
        return None


def _planets(subj) -> list[dict]:
    result = []
    for name, attr in PLANET_ATTRS:
        p = getattr(subj, attr, None)
        if p is None:
            continue
        result.append({
            "name": name,
            "sign": _sign_full(_field(p, "sign", "")),
            "degree": round(float(_field(p, "position", 0)), 4),
            "house": _house_num(_field(p, "house", "")),
            "retrograde": bool(_field(p, "retrograde", False)),
        })
    selena = _selena_planet(subj)
    if selena:
        result.append(selena)
    return result


def _houses(subj) -> list[dict]:
    result = []
    for i, attr in enumerate(HOUSE_ATTRS, start=1):
        h = getattr(subj, attr, None)
        if h is None:
            continue
        result.append({
            "number": i,
            "sign": _sign_full(_field(h, "sign", "")),
            "degree": round(float(_field(h, "position", 0)), 4),
        })
    return result


# ── Public API ────────────────────────────────────────────────────────────────

def calculate_natal_chart(
    name: str,
    year: int, month: int, day: int,
    hour: int, minute: int,
    lat: float, lng: float,
    tz_str: str, city: str = "",
) -> dict:
    subj = _make_subject(name, year, month, day, hour, minute, lat, lng, tz_str, city)

    raw = AspectsFactory.single_chart_aspects(subj)
    aspects = [
        {
            "planet1": asp.p1_name,
            "planet2": asp.p2_name,
            "aspect": asp.aspect,
            "orb": round(asp.orbit, 2),
            "applying": asp.aspect_movement == "Applying",
        }
        for asp in raw.aspects
        if asp.orbit <= 5.0
    ]

    return {
        "planets": _planets(subj),
        "houses": _houses(subj),
        "aspects": aspects,
    }


def calculate_transits(
    birth_year: int, birth_month: int, birth_day: int,
    birth_hour: int, birth_minute: int,
    natal_lat: float, natal_lng: float, natal_tz: str,
    target_date: str,
) -> dict:
    natal_subj = _make_subject(
        "natal",
        birth_year, birth_month, birth_day, birth_hour, birth_minute,
        natal_lat, natal_lng, natal_tz,
    )
    natal_ps = _planets(natal_subj)
    natal_abs = {p["name"]: _abs_deg(p["sign"], p["degree"]) for p in natal_ps}

    d = Date.fromisoformat(target_date)
    transit_subj = _make_subject(
        "transit", d.year, d.month, d.day, 12, 0,
        natal_lat, natal_lng, natal_tz,
    )
    transit_ps = _planets(transit_subj)
    transit_abs = {p["name"]: _abs_deg(p["sign"], p["degree"]) for p in transit_ps}

    active = []
    for tp in transit_ps:
        for np in natal_ps:
            asp_name, orb = _find_aspect(transit_abs[tp["name"]], natal_abs[np["name"]])
            if asp_name:
                active.append({
                    "transit_planet": tp["name"],
                    "aspect": asp_name,
                    "natal_planet": np["name"],
                    "orb": orb,
                    "significance": SIGNIFICANCE.get(tp["name"], 2),
                })

    active.sort(key=lambda x: (-x["significance"], x["orb"]))

    return {
        "date": target_date,
        "transit_planets": [
            {"name": p["name"], "sign": p["sign"], "degree": p["degree"]}
            for p in transit_ps
        ],
        "active_transits": active,
    }


def calculate_synastry(person1_data: dict, person2_data: dict) -> dict:
    def _parse(data):
        y, mo, d = data["birth_date"].split("-")
        h, mi = data["birth_time"].split(":")
        return (
            int(y), int(mo), int(d), int(h), int(mi),
            float(data["birth_lat"]), float(data["birth_lng"]),
            data["timezone"],
        )

    y1, mo1, d1, h1, mi1, lat1, lng1, tz1 = _parse(person1_data)
    y2, mo2, d2, h2, mi2, lat2, lng2, tz2 = _parse(person2_data)

    subj1 = _make_subject(
        person1_data.get("name") or "Person1",
        y1, mo1, d1, h1, mi1, lat1, lng1, tz1,
    )
    subj2 = _make_subject(
        person2_data.get("name") or "Person2",
        y2, mo2, d2, h2, mi2, lat2, lng2, tz2,
    )

    ps1 = _planets(subj1)
    ps2 = _planets(subj2)

    abs1 = {p["name"]: _abs_deg(p["sign"], p["degree"]) for p in ps1}
    abs2 = {p["name"]: _abs_deg(p["sign"], p["degree"]) for p in ps2}

    cross_aspects = []
    score_total = 0
    score_max = 0

    for p1 in ps1:
        w1 = PLANET_WEIGHT.get(p1["name"], 1)
        for p2 in ps2:
            asp_name, orb = _find_aspect(abs1[p1["name"]], abs2[p2["name"]])
            if asp_name and orb <= 5.0:
                cross_aspects.append({
                    "person1_planet": p1["name"],
                    "person2_planet": p2["name"],
                    "aspect": asp_name,
                    "orb": orb,
                })
                w2 = PLANET_WEIGHT.get(p2["name"], 1)
                combined = w1 + w2
                score_total += ASPECT_SCORE.get(asp_name, 0) * combined
                score_max += 3 * combined  # theoretical max per pair

    if score_max > 0:
        compatibility_score = round(((score_total + score_max) / (2 * score_max)) * 100)
    else:
        compatibility_score = 50

    return {
        "person1_planets": ps1,
        "person2_planets": ps2,
        "cross_aspects": cross_aspects,
        "compatibility_score": max(0, min(100, compatibility_score)),
    }
