"""Shared golden fixtures and helpers for the behavior-locking test suite.

Everything here describes CURRENT behavior of the service, captured before
any logic changes. It is not a specification of desired behavior.
"""
import math

# Эталонные входные данные для golden-теста натальной карты.
GOLDEN_ARGS = dict(
    name="Golden",
    year=1990, month=6, day=15,
    hour=14, minute=30,
    lat=55.7558, lng=37.6173,
    tz_str="Europe/Moscow",
    city="Moscow",
)

# То же самое, но в форме тела запроса для HTTP-эндпоинтов.
GOLDEN_REQUEST_BODY = dict(
    name="Golden",
    birth_date="1990-06-15",
    birth_time="14:30",
    birth_lat=55.7558,
    birth_lng=37.6173,
    timezone="Europe/Moscow",
    birth_city="Moscow",
)


def assert_deep_approx(actual, expected, abs_tol=1e-6, path="root"):
    """Recursively compare two JSON-like structures.

    Numbers are compared with an absolute tolerance (default 1e-6) instead
    of exact equality, since the underlying ephemeris/aspect calculations
    involve floating point. Everything else (strings, bools, dict keys,
    list length/order) must match exactly.
    """
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected dict, got {type(actual)}"
        assert actual.keys() == expected.keys(), (
            f"{path}: key sets differ — actual={sorted(actual.keys())} "
            f"expected={sorted(expected.keys())}"
        )
        for key in expected:
            assert_deep_approx(actual[key], expected[key], abs_tol, f"{path}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list), f"{path}: expected list, got {type(actual)}"
        assert len(actual) == len(expected), (
            f"{path}: length differs — actual={len(actual)} expected={len(expected)}"
        )
        for i, (a_item, e_item) in enumerate(zip(actual, expected)):
            assert_deep_approx(a_item, e_item, abs_tol, f"{path}[{i}]")
    elif isinstance(expected, bool) or isinstance(actual, bool):
        assert actual is expected, f"{path}: actual={actual!r} expected={expected!r}"
    elif isinstance(expected, (int, float)):
        assert isinstance(actual, (int, float)), f"{path}: expected number, got {type(actual)}"
        assert math.isclose(actual, expected, abs_tol=abs_tol, rel_tol=0), (
            f"{path}: actual={actual!r} expected={expected!r} (tol={abs_tol})"
        )
    else:
        assert actual == expected, f"{path}: actual={actual!r} expected={expected!r}"
