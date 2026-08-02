from pathlib import Path

import requests
from dotenv import load_dotenv
from timezonefinder import TimezoneFinder

from city_repository import get_city_repository

load_dotenv(Path(__file__).parent / ".env")

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_HEADERS = {"User-Agent": "AstroApp/1.0"}
_TF = TimezoneFinder()
_CITY_REPO = get_city_repository()


def search_cities(query: str, limit: int = 6) -> list[dict]:
    """Autocomplete search backed by the configured city directory adapter."""
    return _CITY_REPO.search_cities(query.strip(), limit=limit)


def get_coordinates(city_name: str) -> dict:
    """Return {lat, lng, timezone} for the best-matching city.

    Uses a simple best-match query without featuretype filtering so that
    Nominatim's default relevance ranking is preserved (e.g. "Saint Petersburg"
    → Санкт-Петербург, RU before St. Petersburg, US when typed in Russian context).
    search_cities() is for autocomplete UI only.
    """
    resp = requests.get(
        _NOMINATIM_URL,
        params={"q": city_name, "format": "json", "limit": 1, "accept-language": "ru,en"},
        headers=_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        raise ValueError(f"City not found: {city_name!r}")
    lat = float(results[0]["lat"])
    lng = float(results[0]["lon"])
    return {"lat": lat, "lng": lng, "timezone": _TF.timezone_at(lat=lat, lng=lng) or "UTC"}
