"""Проверка полноты состава точек натальной карты.

calculator.py декларирует набор точек, которые сервис должен считать:
все записи PLANET_ATTRS (Sun, Moon, ..., Mean_Node) плюс отдельно
вычисляемая Selena (_selena_planet). Тест сверяет, что все эти точки
реально присутствуют в ответе calculate_natal_chart().

ИЗВЕСТНЫЙ ДЕФЕКТ (не исправляется здесь — логика не трогается):
PLANET_ATTRS ссылается на точку "Mean_Node" через атрибут `mean_node`
(calculator.py: PLANET_ATTRS = [..., ("Mean_Node", "mean_node"), ...]),
но объект, который возвращает
kerykeion.astrological_subject_factory.AstrologicalSubjectFactory (5.12.8),
атрибута `mean_node` не имеет вообще — есть `mean_north_lunar_node` и
`true_north_lunar_node`, но не `mean_node`. Поэтому `_planets()` тихо
пропускает Mean_Node (getattr(..., "mean_node", None) is None), и точка,
которую сервис "декларирует" считать, в ответе отсутствует.

Тест намеренно НЕ подогнан под текущий факт (не проверяет "13 точек из
14") — он проверяет полный заявленный набор и помечен как xfail(strict),
чтобы дефект был виден в отчёте тестов, а не замаскирован. Если дефект
когда-нибудь устранят (в calculator.py или в used-версии kerykeion), этот
тест станет XPASS и strict=True превратит это в явный провал — сигнал,
что xfail-маркер пора снять.
"""
import pytest

from calculator import PLANET_ATTRS, calculate_natal_chart

from _shared import GOLDEN_ARGS

DECLARED_POINT_NAMES = {name for name, _ in PLANET_ATTRS} | {"Selena"}


@pytest.mark.xfail(
    reason=(
        "calculator.PLANET_ATTRS декларирует точку Mean_Node (атрибут 'mean_node'), "
        "но kerykeion 5.12.8 не выставляет такой атрибут на объекте "
        "AstrologicalSubjectFactory (есть mean_north_lunar_node/true_north_lunar_node, "
        "но не mean_node) — точка молча отсутствует в ответе. Логика намеренно не "
        "меняется до согласования с астрологом; тест фиксирует дефект явно."
    ),
    strict=True,
)
def test_all_declared_points_are_present_in_response():
    result = calculate_natal_chart(
        GOLDEN_ARGS["name"],
        GOLDEN_ARGS["year"], GOLDEN_ARGS["month"], GOLDEN_ARGS["day"],
        GOLDEN_ARGS["hour"], GOLDEN_ARGS["minute"],
        GOLDEN_ARGS["lat"], GOLDEN_ARGS["lng"],
        GOLDEN_ARGS["tz_str"], GOLDEN_ARGS["city"],
    )

    actual_names = {p["name"] for p in result["planets"]}

    missing = DECLARED_POINT_NAMES - actual_names
    assert not missing, f"Точки заявлены, но отсутствуют в ответе: {sorted(missing)}"
    assert actual_names == DECLARED_POINT_NAMES
