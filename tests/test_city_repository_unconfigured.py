"""Расчёт не должен зависеть от справочника городов.

Если координаты и таймзона переданы в запросе явно, обращения к
справочнику городов не происходит вообще — расчёт обязан работать даже
когда CITY_REPOSITORY_SOURCE не задан (см. city_repository.py,
NullCityRepository). Автодополнение (/geocode/search), наоборот, без
настроенного справочника недоступно — фиксируем и это как контракт.
"""
import os

from _shared import GOLDEN_REQUEST_BODY


def test_calculate_works_without_city_repository_configured(client):
    assert os.getenv("CITY_REPOSITORY_SOURCE") in (None, "")

    r = client.post("/calculate", json=GOLDEN_REQUEST_BODY)

    assert r.status_code == 200


def test_geocode_search_returns_503_without_city_repository_configured(client):
    assert os.getenv("CITY_REPOSITORY_SOURCE") in (None, "")

    r = client.get("/geocode/search", params={"q": "Moscow"})

    assert r.status_code == 503
