"""Контрактные тесты POST /calculate.

Фиксируют фактически возвращаемые коды ответа для валидного и невалидных
запросов — как есть, без исправления обработки ошибок в main.py.

ТЕКУЩЕЕ ПОВЕДЕНИЕ (зафиксировано этими тестами, не считается желаемым):
main.py разбирает birth_date/birth_time через `int(p) for p in ...split(...)`
без валидации и без try/except, а затем передаёт значения в kerykeion/
pyswisseph напрямую. Некорректная дата, некорректное время и несуществующая
таймзона не обрабатываются как 4xx — они приводят к необработанному
исключению внутри обработчика, и FastAPI отдаёт клиенту 500 Internal
Server Error, а не 422 Unprocessable Entity.
"""
import pytest

from _shared import GOLDEN_REQUEST_BODY


def test_calculate_returns_200_for_valid_request(client):
    r = client.post("/calculate", json=GOLDEN_REQUEST_BODY)

    assert r.status_code == 200
    body = r.json()
    assert "planets" in body
    assert "houses" in body
    assert "aspects" in body


@pytest.mark.parametrize(
    "bad_date",
    ["not-a-date", "1990-13-45", "1990-02-30", ""],
)
def test_calculate_with_invalid_date_returns_500(client, bad_date):
    body = dict(GOLDEN_REQUEST_BODY, birth_date=bad_date)
    r = client.post("/calculate", json=body)

    # Фактическое поведение сейчас — 500 (необработанное исключение),
    # а не 422. См. пояснение в докстринге модуля.
    assert r.status_code == 500


@pytest.mark.parametrize(
    "bad_time",
    ["not-a-time", "25:99", ""],
)
def test_calculate_with_invalid_time_returns_500(client, bad_time):
    body = dict(GOLDEN_REQUEST_BODY, birth_time=bad_time)
    r = client.post("/calculate", json=body)

    assert r.status_code == 500


def test_calculate_with_nonexistent_timezone_returns_500(client):
    body = dict(GOLDEN_REQUEST_BODY, timezone="Mars/Colony_One")
    r = client.post("/calculate", json=body)

    assert r.status_code == 500
