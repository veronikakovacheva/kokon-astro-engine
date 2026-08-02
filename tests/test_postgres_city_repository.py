"""Интеграционные тесты PostgresCityRepository.

Требуют настоящий PostgreSQL — пропускаются, если он не сконфигурирован.
Используется ОТДЕЛЬНАЯ переменная окружения TEST_POSTGRES_DSN (не
CITY_REPOSITORY_DSN приложения!), чтобы тестовый набор не мог случайно
truncate'нуть боевую/общую базу: фикстура ниже безусловно выполняет
TRUNCATE + INSERT по указанному DSN при каждом запуске.

Как запустить локально:
    createdb kokon_astro_test
    psql -d kokon_astro_test -f migrations/001_cities.sql
    TEST_POSTGRES_DSN="dbname=kokon_astro_test" pytest tests/test_postgres_city_repository.py -v

Тестовые данные — реальная (не синтетическая) выборка из GeoNames:
tests/fixtures/geonames_sample.sql — все "Moscow"/"Saint Petersburg" из
cities500.txt + их альтернативные имена (см. комментарий в файле).
"""
import os
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

from city_repository import PostgresCityRepository

TEST_DSN = os.environ.get("TEST_POSTGRES_DSN", "")
MIGRATION_PATH = Path(__file__).parent.parent / "migrations" / "001_cities.sql"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "geonames_sample.sql"

pytestmark = pytest.mark.skipif(
    not TEST_DSN,
    reason=(
        "TEST_POSTGRES_DSN не задан — интеграционные тесты "
        "PostgresCityRepository пропущены. См. докстринг модуля."
    ),
)


@pytest.fixture(scope="module")
def repo():
    with psycopg.connect(TEST_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(MIGRATION_PATH.read_text(encoding="utf-8"))
            cur.execute(FIXTURE_PATH.read_text(encoding="utf-8"))
        conn.commit()

    return PostgresCityRepository(TEST_DSN)


def test_moscow_cyrillic_first_result_is_russian_capital(repo):
    results = repo.search_cities("Москва")

    assert results, "ожидался хотя бы один результат"
    first = results[0]
    assert first["timezone"] == "Europe/Moscow"
    assert first["short_name"].endswith(", RU")
    # Российская Москва (10.4M) должна перевесить американские тёзки
    # (макс. 25к) за счёт сортировки по населению.
    assert first["lat"] == pytest.approx(55.75204, abs=1e-3)
    assert first["lng"] == pytest.approx(37.61781, abs=1e-3)


def test_leningrad_finds_saint_petersburg_with_modern_name(repo):
    results = repo.search_cities("Ленинград")

    assert len(results) == 1
    result = results[0]
    assert result["short_name"] == "Saint Petersburg, RU"
    assert result["display_name"] == "Санкт-Петербург, RU"
    assert "Ленинград" not in result["display_name"]
    assert "Ленинград" not in result["short_name"]


def test_search_works_with_latin_script(repo):
    results = repo.search_cities("Moscow")

    assert results
    names = {r["short_name"] for r in results}
    assert "Moscow, RU" in names
    assert results[0]["short_name"] == "Moscow, RU"


def test_nonexistent_city_returns_empty_list(repo):
    assert repo.search_cities("Zzzzznonexistentcityxyz") == []
