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
    populated from GeoNames — see migrations/001_cities.sql,
    migrations/002_trigram_search.sql and scripts/import_geonames.py.

    Matching happens in two tiers against the city's primary name, its ascii
    name, and any of its alternate names (which include historic names such
    as "Ленинград" for Saint Petersburg):
      1. PREFIX matches ("starts with") — always ranked above tier 2.
      2. SUBSTRING matches ("contains") — needed for Russian compound place
         names, where users commonly search by the meaningful part rather
         than from the start (e.g. "Петербург" -> "Санкт-Петербург",
         "Новгород" -> "Нижний Новгород"). See
         docs/adr/0003-trigram-search-for-substring-matching.md.

    Within each tier, a city that matched via its primary name or a
    *preferred* alternate name (city_alternate_names.is_preferred) ranks
    above a city that only matched via a non-preferred alternate name, and
    finally results are sorted by population descending. A city can match
    via several rows at once (e.g. both a preferred and a non-preferred
    alternate name); results are de-duplicated by geonameid, taking its best
    tier/preference. The displayed name always comes from `cities` (the
    current/modern name) plus, for the Russian display name, the preferred
    non-historic `ru` alternate name — never from whichever alternate-name
    row actually produced the match — so a historic-name query still returns
    the modern name.
    """

    _SEARCH_SQL = """
        WITH prefix_hits AS (
            SELECT geonameid, TRUE AS is_preferred_hit FROM cities
            WHERE lower(name) LIKE %(prefix)s OR lower(ascii_name) LIKE %(prefix)s
            UNION ALL
            SELECT geonameid, is_preferred FROM city_alternate_names
            WHERE lower(alternate_name) LIKE %(prefix)s
        ),
        prefix_matches AS (
            SELECT geonameid, bool_or(is_preferred_hit) AS preferred_match
            FROM prefix_hits
            GROUP BY geonameid
        ),
        substring_hits AS (
            SELECT geonameid, TRUE AS is_preferred_hit FROM cities
            WHERE lower(name) LIKE %(substring)s OR lower(ascii_name) LIKE %(substring)s
            UNION ALL
            SELECT geonameid, is_preferred FROM city_alternate_names
            WHERE lower(alternate_name) LIKE %(substring)s
        ),
        substring_matches AS (
            SELECT geonameid, bool_or(is_preferred_hit) AS preferred_match
            FROM substring_hits
            WHERE geonameid NOT IN (SELECT geonameid FROM prefix_matches)
            GROUP BY geonameid
        ),
        matches AS (
            SELECT geonameid, 0 AS tier, preferred_match FROM prefix_matches
            UNION ALL
            SELECT geonameid, 1 AS tier, preferred_match FROM substring_matches
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
        ORDER BY m.tier ASC, m.preferred_match DESC, c.population DESC NULLS LAST, c.name
        LIMIT %(limit)s
    """

    def __init__(self, dsn: str):
        self._dsn = dsn

    @staticmethod
    def _escape_like(value: str) -> str:
        """Escapes LIKE metacharacters in user input (\\, %, _) so a query
        like "50%" or "a_b" is matched literally, not as a wildcard pattern.
        """
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def search_cities(self, query: str, limit: int = 6) -> list[dict]:
        import psycopg
        from psycopg.rows import dict_row

        q = query.strip()
        if not q:
            return []
        escaped = self._escape_like(q.lower())
        prefix = escaped + "%"
        substring = "%" + escaped + "%"

        with psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    self._SEARCH_SQL,
                    {"prefix": prefix, "substring": substring, "limit": limit},
                )
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
