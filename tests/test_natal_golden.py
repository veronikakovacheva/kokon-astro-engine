"""Golden-тест натальной карты.

Фиксирует текущий вывод calculate_natal_chart() для эталонных входных
данных как есть — это тест-регрессия на поведение, а не проверка
астрологической корректности. Если calculator.py когда-либо изменится
(намеренно, после согласования с астрологом), фикстуру нужно будет
пересчитать заново, а не подгонять код под старую фикстуру.
"""
import json
from pathlib import Path

from calculator import calculate_natal_chart

from _shared import GOLDEN_ARGS, assert_deep_approx

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "natal_1990_06_15_moscow.json"


def test_natal_chart_matches_golden_fixture():
    expected = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    actual = calculate_natal_chart(
        GOLDEN_ARGS["name"],
        GOLDEN_ARGS["year"], GOLDEN_ARGS["month"], GOLDEN_ARGS["day"],
        GOLDEN_ARGS["hour"], GOLDEN_ARGS["minute"],
        GOLDEN_ARGS["lat"], GOLDEN_ARGS["lng"],
        GOLDEN_ARGS["tz_str"], GOLDEN_ARGS["city"],
    )

    assert_deep_approx(actual, expected, abs_tol=1e-6)
