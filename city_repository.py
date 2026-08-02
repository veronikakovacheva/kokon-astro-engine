"""Adapter for the city directory used by GET /geocode/search (autocomplete).

The natal chart calculation never depends on this: if birth_lat/birth_lng/
timezone are supplied explicitly, no directory lookup happens at all. Single-
city geocoding (POST /calculate with only a city name) also does not use this
module — it resolves via Nominatim in geocoder.py.

The concrete source is selected at runtime via CITY_REPOSITORY_SOURCE:
  - unset / anything other than "postgres" -> NullCityRepository (stub)
  - "postgres"                             -> PostgresCityRepository
"""
import os
from abc import ABC, abstractmethod


class CityRepositoryError(RuntimeError):
    """Raised when the city directory is unavailable or misconfigured."""


class CityRepository(ABC):
    @abstractmethod
    def search_cities(self, query: str, limit: int = 6) -> list[dict]:
        ...


class NullCityRepository(CityRepository):
    """Used when no city directory is configured (CITY_REPOSITORY_SOURCE unset)."""

    def search_cities(self, query: str, limit: int = 6) -> list[dict]:
        raise CityRepositoryError(
            "City directory is not configured. Set CITY_REPOSITORY_SOURCE=postgres "
            "and CITY_REPOSITORY_DSN, or pass birth_lat/birth_lng/timezone explicitly "
            "instead of using autocomplete."
        )


class PostgresCityRepository(CityRepository):
    """City directory backed by the `cities` / `city_alternate_names` tables
    populated from GeoNames — see migrations/001_cities.sql and
    scripts/import_geonames.py.

    Matching is a case-insensitive PREFIX search (not substring) against the
    city's primary name, its ascii name, and any of its alternate names
    (which include historic names such as "Ленинград" for Saint Petersburg).
    A city can match via several alternate names at once; results are
    de-duplicated by geonameid before ranking. The displayed name always
    comes from `cities` (the current/modern name) — never from the
    alternate-name row that produced the match — so a historic-name query
    still returns the modern name.
    """

    _SEARCH_SQL = """
        WITH matches AS (
            SELECT geonameid FROM cities
            WHERE lower(name) LIKE %(prefix)s OR lower(ascii_name) LIKE %(prefix)s
            UNION
            SELECT geonameid FROM city_alternate_names
            WHERE lower(alternate_name) LIKE %(prefix)s
        )
        SELECT
            c.name,
            c.country_code,
            c.latitude,
            c.longitude,
            c.timezone,
            (
                SELECT an.alternate_name
                FROM city_alternate_names an
                WHERE an.geonameid = c.geonameid
                  AND an.iso_language = 'ru'
                  AND an.is_historic = FALSE
                ORDER BY an.is_preferred DESC, an.alternate_name
                LIMIT 1
            ) AS name_ru
        FROM cities c
        JOIN matches m ON m.geonameid = c.geonameid
        ORDER BY c.population DESC NULLS LAST, c.name
        LIMIT %(limit)s
    """

    def __init__(self, dsn: str):
        self._dsn = dsn

    def search_cities(self, query: str, limit: int = 6) -> list[dict]:
        import psycopg
        from psycopg.rows import dict_row

        q = query.strip()
        if not q:
            return []
        prefix = q.lower() + "%"

        with psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(self._SEARCH_SQL, {"prefix": prefix, "limit": limit})
                rows = cur.fetchall()

        results = []
        for row in rows:
            name = row["name"]
            name_ru = row.get("name_ru")
            country = row.get("country_code") or ""

            short_name = f"{name}, {country}" if country else name
            display_name = f"{name_ru}, {country}" if name_ru and country else short_name

            results.append({
                "short_name": short_name,
                "display_name": display_name,
                "lat": row["latitude"],
                "lng": row["longitude"],
                "timezone": row.get("timezone") or "UTC",
            })

        return results


def get_city_repository() -> CityRepository:
    source = os.getenv("CITY_REPOSITORY_SOURCE", "").strip().lower()

    if source == "postgres":
        dsn = os.getenv("CITY_REPOSITORY_DSN", "")
        if not dsn:
            raise CityRepositoryError(
                "CITY_REPOSITORY_SOURCE=postgres but CITY_REPOSITORY_DSN is not set"
            )
        return PostgresCityRepository(dsn)

    return NullCityRepository()
