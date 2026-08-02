"""Идемпотентность scripts/import_geonames.py: upsert, а не TRUNCATE.

Требуют настоящий PostgreSQL — пропускаются без TEST_POSTGRES_DSN (та же
переменная и те же меры предосторожности, что и в
test_postgres_city_repository.py: НЕ используйте здесь боевой
CITY_REPOSITORY_DSN — фикстура делает TRUNCATE перед каждым тестом).

Данные — синтетические (не настоящий GeoNames), но в точном формате
cities500.txt/alternateNamesV2.txt, сгенерированы во временный файл на
диске и прогнаны через настоящие import_cities()/import_alternate_names()
из scripts/import_geonames.py — те же функции, что использует реальный
импорт, не переизобретённая логика.

Сценарий проверяет весь контракт upsert-подхода за один прогон "v1 -> v1
ещё раз -> v2":
  - повторный запуск с тем же файлом не создаёт дубликатов (v1 -> v1);
  - изменившееся значение обновляется на месте (population города A);
  - новая строка добавляется (город C, альт. имя для C);
  - строка, пропавшая из дампа, удаляется из таблицы (город B и, каскадно,
    его альт. имя; альт. имя города A, пропавшее из дампа, но сам город A
    остался — проверяет удаление на уровне city_alternate_names отдельно
    от каскада по cities).
"""
import sys
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import import_geonames as ig  # noqa: E402

import os

TEST_DSN = os.environ.get("TEST_POSTGRES_DSN", "")
MIGRATION_PATH = Path(__file__).parent.parent / "migrations" / "001_cities.sql"

pytestmark = pytest.mark.skipif(
    not TEST_DSN,
    reason=(
        "TEST_POSTGRES_DSN не задан — тесты идемпотентности импорта "
        "пропущены. См. докстринг модуля."
    ),
)


def _city_line(geonameid, name, population, timezone="Etc/UTC"):
    fields = [
        str(geonameid), name, name, "", "10.0", "20.0", "P", "PPL", "XX", "",
        "01", "", "", "", str(population), "", "", timezone, "2024-01-01",
    ]
    return "\t".join(fields)


def _alt_line(alt_id, geonameid, language, name, preferred="", historic=""):
    fields = [str(alt_id), str(geonameid), language, name, preferred, "", "", historic, "", ""]
    return "\t".join(fields)


# Город A(9000001) сохраняется в обоих снимках (население меняется 1000->1500).
# Город B(9000002) есть только в v1 — во v2 должен быть удалён (вместе со
# своим альт. именем — каскадом по FK).
# Город C(9000003) есть только в v2 — новый.
CITIES_V1 = "\n".join([
    _city_line(9000001, "TestAlpha", 1000),
    _city_line(9000002, "TestBeta", 2000),
]) + "\n"

CITIES_V2 = "\n".join([
    _city_line(9000001, "TestAlpha", 1500),
    _city_line(9000003, "TestGamma", 3000),
]) + "\n"

# Альт. имя 9100001 (город A) есть в обоих снимках — должно остаться.
# Альт. имя 9100002 (город A, историческое) есть только в v1 — во v2 должно
# быть удалено, при этом сам город A остаётся (проверка удаления не через
# каскад, а через прямой DELETE ... NOT IN staging).
# Альт. имя 9100003 (город B) исчезает вместе с городом B — каскадом.
# Альт. имя 9100004/9100005 — новые во v2 (для A и для нового города C).
ALT_NAMES_V1 = "\n".join([
    _alt_line(9100001, 9000001, "en", "Alpha City", preferred="1"),
    _alt_line(9100002, 9000001, "ru", "Альфа", historic="1"),
    _alt_line(9100003, 9000002, "en", "Beta City"),
]) + "\n"

ALT_NAMES_V2 = "\n".join([
    _alt_line(9100001, 9000001, "en", "Alpha City", preferred="1"),
    _alt_line(9100004, 9000001, "en", "Alpha Historic", historic="1"),
    _alt_line(9100005, 9000003, "en", "Gamma City"),
]) + "\n"


@pytest.fixture
def db(tmp_path):
    with psycopg.connect(TEST_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(MIGRATION_PATH.read_text(encoding="utf-8"))
            cur.execute("TRUNCATE TABLE cities, city_alternate_names")
        conn.commit()
    return TEST_DSN


def _run_import(dsn, cities_text, alt_names_text, tmp_path, tag):
    cities_path = tmp_path / f"cities_{tag}.txt"
    alt_names_path = tmp_path / f"alt_{tag}.txt"
    cities_path.write_text(cities_text, encoding="utf-8")
    alt_names_path.write_text(alt_names_text, encoding="utf-8")

    with psycopg.connect(dsn) as conn:
        keep_ids = ig.import_cities(conn, cities_path)
        ig.import_alternate_names(conn, alt_names_path, keep_ids)


def _fetch_state(dsn):
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT geonameid, name, population FROM cities ORDER BY geonameid")
            cities = cur.fetchall()
            cur.execute(
                "SELECT id, geonameid, alternate_name FROM city_alternate_names ORDER BY id"
            )
            alt_names = cur.fetchall()
    return cities, alt_names


def test_rerunning_same_dump_does_not_duplicate_rows(db, tmp_path):
    _run_import(db, CITIES_V1, ALT_NAMES_V1, tmp_path, "v1_first")
    cities_after_first, alt_names_after_first = _fetch_state(db)

    _run_import(db, CITIES_V1, ALT_NAMES_V1, tmp_path, "v1_second")
    cities_after_second, alt_names_after_second = _fetch_state(db)

    assert cities_after_second == cities_after_first
    assert alt_names_after_second == alt_names_after_first
    assert len(cities_after_second) == 2
    assert len(alt_names_after_second) == 3


def test_reimport_updates_changed_rows_adds_new_and_removes_stale(db, tmp_path):
    _run_import(db, CITIES_V1, ALT_NAMES_V1, tmp_path, "v1")
    _run_import(db, CITIES_V2, ALT_NAMES_V2, tmp_path, "v2")

    cities, alt_names = _fetch_state(db)

    # Город A обновлён на месте (тот же geonameid, новое население).
    assert (9000001, "TestAlpha", 1500) in cities
    # Город C — новый.
    assert (9000003, "TestGamma", 3000) in cities
    # Город B пропал из дампа -> удалён из таблицы.
    assert all(c[0] != 9000002 for c in cities)
    assert len(cities) == 2

    alt_ids = {row[0] for row in alt_names}
    # Альт. имя, оставшееся в дампе, сохранилось.
    assert 9100001 in alt_ids
    # Новые альт. имена (для A и для нового города C) появились.
    assert 9100004 in alt_ids
    assert 9100005 in alt_ids
    # Альт. имя, пропавшее из дампа для СУЩЕСТВУЮЩЕГО города A, удалено
    # напрямую (не каскадом).
    assert 9100002 not in alt_ids
    # Альт. имя удалённого города B пропало каскадом.
    assert 9100003 not in alt_ids
    assert len(alt_names) == 3


def test_interrupted_import_leaves_previous_data_intact_not_empty(db, tmp_path):
    """Регрессия на причину отказа от TRUNCATE: если бы импорт стирал
    таблицу заранее, любой сбой до COPY оставлял бы её пустой. С upsert'ом
    промежуточных состояний с пустой таблицей не бывает — до commit'а
    новой партии старые данные видны как есть.
    """
    _run_import(db, CITIES_V1, ALT_NAMES_V1, tmp_path, "v1")
    cities_before, _ = _fetch_state(db)
    assert len(cities_before) == 2

    bad_cities_path = tmp_path / "cities_broken.txt"
    bad_cities_path.write_text("this is not a valid geonames line at all\n", encoding="utf-8")

    with psycopg.connect(db) as conn:
        with pytest.raises(Exception):
            ig.import_cities(conn, bad_cities_path)

    cities_after_failed_attempt, _ = _fetch_state(db)
    assert cities_after_failed_attempt == cities_before
