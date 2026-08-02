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
    """
    TODO(next stage): the `cities` table does not exist yet — it will be created
    together with a migration and a data-loading script in a later stage. This
    class mirrors the schema of the previous Supabase `cities` table
    (name, name_ru, country, lat, lng, timezone, population) so that once the
    table exists, this adapter should work without further changes.
    """

    def __init__(self, dsn: str):
        self._dsn = dsn

    def search_cities(self, query: str, limit: int = 6) -> list[dict]:
        import psycopg

        pattern = f"%{query.strip()}%"
        sql = """
            SELECT name, name_ru, country, lat, lng, timezone
            FROM cities
            WHERE name ILIKE %(pattern)s OR name_ru ILIKE %(pattern)s
            ORDER BY population DESC NULLS LAST
            LIMIT %(limit)s
        """
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"pattern": pattern, "limit": limit})
                columns = [desc[0] for desc in cur.description]
                rows = [dict(zip(columns, row)) for row in cur.fetchall()]

        results = []
        for row in rows:
            name = row["name"]
            country = row.get("country") or ""
            name_ru = row.get("name_ru")

            short_name = f"{name}, {country}" if country else name
            display_name = f"{name_ru}, {country}" if name_ru and country else short_name

            results.append({
                "short_name": short_name,
                "display_name": display_name,
                "lat": row["lat"],
                "lng": row["lng"],
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
