#!/usr/bin/env python3
"""Импорт справочника городов из дампов GeoNames в PostgreSQL.

Источник данных: https://download.geonames.org/export/dump/ (лицензия
CC BY 4.0, см. README.md). Ожидаются два файла в каталоге дампов:

  cities500.txt          geoname-таблица (19 колонок, TSV, без заголовка):
                          населённые пункты с населением >= 500 либо
                          столицы/административные центры.
  alternateNamesV2.txt   alternate names таблица (10 колонок, TSV, без
                          заголовка): названия на разных языках, в т.ч.
                          исторические.

Из cities500.txt берутся только строки с feature_code населённого пункта
(начинается с "PPL"), за вычетом PPLQ/PPLW/PPLH — мест, которых больше не
существует (заброшены/уничтожены/исторические). По размеру НЕ фильтруем —
маленькие посёлки остаются наравне с миллионниками, см.
docs/adr/0002-import-filters-by-place-type-not-size.md.

Из alternateNamesV2.txt (обычно несколько сотен МБ и десятки миллионов
строк по ВСЕЙ базе GeoNames, не только по городам) берутся только записи,
относящиеся к geonameid из уже отфильтрованного cities500.txt, и только
языки ru/en, плюс записи с непустым признаком исторического названия —
независимо от языка (чтобы находить города по старым именам, например
"Ленинград"). Файл читается потоково, построчно — целиком в память не
загружается.

Схема — см. migrations/001_cities.sql, применить нужно заранее.
Подключение к БД — через переменную окружения CITY_REPOSITORY_DSN (.env).

Идемпотентность: НЕ через TRUNCATE. Каждая таблица грузится через COPY во
временную staging-таблицу, затем переносится в целевую через
`INSERT ... ON CONFLICT (pk) DO UPDATE` (upsert), и в конце одним `DELETE`
убираются строки, которых больше нет в текущем дампе (переименованные/
удалённые в GeoNames города и альтернативные названия). TRUNCATE
намеренно не используется: он держит ACCESS EXCLUSIVE-блокировку на всю
длительность импорта (блокируя /geocode/search) и делает частичный сбой
разрушительным — прерванный на середине TRUNCATE-импорт мог бы оставить
таблицу пустой или неполной. Upsert же ничего не стирает заранее: другие
запросы всегда видят либо полностью старые, либо полностью новые данные,
и повторный запуск (в т.ч. после сбоя, в любой момент) безопасен и не
создаёт дубликатов — просто ещё раз проверяет/обновляет то же самое.

Обе таблицы (cities, затем city_alternate_names) коммитятся отдельно, по
завершении upsert+delete для каждой — так сбой во время загрузки
alternate names не откатывает уже успешно загруженные cities.

Использование:
    python scripts/import_geonames.py [DATA_DIR]

DATA_DIR по умолчанию: ~/Desktop/Кокон Claude/geonames-data/
"""
import argparse
import os
import sys
import time
from pathlib import Path

import psycopg
from dotenv import load_dotenv

DEFAULT_DATA_DIR = Path("~/Desktop/Кокон Claude/geonames-data/").expanduser()

CITIES_FILENAME = "cities500.txt"
ALTERNATE_NAMES_FILENAME = "alternateNamesV2.txt"

# Языки альтернативных названий, которые загружаются независимо от того,
# исторические они или нет.
KEEP_LANGUAGES = {"ru", "en"}

# Из cities500.txt берутся только населённые пункты: feature_code,
# начинающийся с "PPL" (populated place — см. http://www.geonames.org/export/codes.html),
# за вычетом кодов, обозначающих место, которого больше нет:
#   PPLQ — заброшенный населённый пункт (abandoned populated place)
#   PPLW — уничтоженный населённый пункт (destroyed populated place)
#   PPLH — населённый пункт, переставший существовать (historical populated place)
# По размеру НЕ фильтруем — маленький посёлок остаётся в справочнике наравне
# с мегаполисом (см. docs/adr/0002-import-filters-by-place-type-not-size.md).
EXCLUDED_FEATURE_CODES = {"PPLQ", "PPLW", "PPLH"}


def _is_populated_place(feature_code: str) -> bool:
    return feature_code.startswith("PPL") and feature_code not in EXCLUDED_FEATURE_CODES

CITIES_COLUMNS = (
    "geonameid", "name", "ascii_name", "latitude", "longitude",
    "country_code", "admin1_code", "population", "timezone", "feature_code",
)
ALT_NAMES_COLUMNS = (
    "id", "geonameid", "alternate_name", "iso_language", "is_historic", "is_preferred",
)

CITIES_PROGRESS_EVERY = 50_000
ALT_NAMES_SCAN_PROGRESS_EVERY = 1_000_000
ALT_NAMES_MATCH_PROGRESS_EVERY = 20_000


def iter_cities(path: Path):
    """Стримит cities500.txt и отдаёт словари в порядке CITIES_COLUMNS.

    Пропускает строки, чей feature_code — не населённый пункт или
    обозначает место, которого больше не существует (см.
    EXCLUDED_FEATURE_CODES). Печатает итоговое число отфильтрованных по
    типу строк по завершении чтения файла.
    """
    excluded_by_type = 0
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 19:
                print(
                    f"  [WARN] {path.name}:{lineno}: ожидалось 19 полей, "
                    f"получено {len(fields)} — строка пропущена",
                    file=sys.stderr,
                )
                continue

            (
                geonameid, name, ascii_name, _alternatenames, latitude, longitude,
                _feature_class, feature_code, country_code, _cc2,
                admin1_code, _admin2, _admin3, _admin4,
                population, _elevation, _dem, timezone, _mod_date,
            ) = fields[:19]

            if not _is_populated_place(feature_code):
                excluded_by_type += 1
                continue

            try:
                yield {
                    "geonameid": int(geonameid),
                    "name": name,
                    "ascii_name": ascii_name,
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                    "country_code": country_code or None,
                    "admin1_code": admin1_code or None,
                    "population": int(population) if population else None,
                    "timezone": timezone or None,
                    "feature_code": feature_code or None,
                }
            except ValueError as e:
                print(f"  [WARN] {path.name}:{lineno}: {e} — строка пропущена", file=sys.stderr)
                continue

    print(f"  отфильтровано по типу (не населённый пункт / заброшено-уничтожено): {excluded_by_type:,}")


def iter_alternate_names(path: Path, keep_geonameids: set):
    """Стримит alternateNamesV2.txt построчно и отдаёт только записи для
    geonameid из keep_geonameids, на языках ru/en или с флагом is_historic.
    """
    scanned = 0
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            scanned += 1
            if scanned % ALT_NAMES_SCAN_PROGRESS_EVERY == 0:
                print(f"  ...прочитано строк файла: {scanned:,}", file=sys.stderr)

            fields = line.rstrip("\n").split("\t")
            if len(fields) < 8:
                print(
                    f"  [WARN] {path.name}:{lineno}: ожидалось >=8 полей, "
                    f"получено {len(fields)} — строка пропущена",
                    file=sys.stderr,
                )
                continue
            while len(fields) < 10:
                fields.append("")

            (
                alt_id, geonameid, iso_language, alternate_name,
                is_preferred, _is_short, _is_colloquial, is_historic,
                _from, _to,
            ) = fields[:10]

            try:
                geonameid_int = int(geonameid)
            except ValueError:
                continue
            if geonameid_int not in keep_geonameids:
                continue

            is_historic_bool = is_historic == "1"
            if iso_language not in KEEP_LANGUAGES and not is_historic_bool:
                continue
            if not alternate_name:
                continue

            try:
                alt_id_int = int(alt_id)
            except ValueError:
                continue

            yield {
                "id": alt_id_int,
                "geonameid": geonameid_int,
                "alternate_name": alternate_name,
                "iso_language": iso_language or None,
                "is_historic": is_historic_bool,
                "is_preferred": is_preferred == "1",
            }


def _upsert_from_staging(cur, staging_table: str, target_table: str, columns: tuple, pk: str) -> tuple:
    """INSERT ... ON CONFLICT DO UPDATE из staging_table в target_table, затем
    DELETE строк target_table, которых больше нет в staging_table. Возвращает
    (upserted_count, deleted_count). staging_table должна существовать в
    текущей транзакции (см. CREATE TEMP TABLE ... ON COMMIT DROP у вызывающего).
    """
    columns_sql = ", ".join(columns)
    update_sql = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c != pk)

    cur.execute(f"""
        INSERT INTO {target_table} ({columns_sql})
        SELECT DISTINCT ON ({pk}) {columns_sql}
        FROM {staging_table}
        ORDER BY {pk}
        ON CONFLICT ({pk}) DO UPDATE SET {update_sql}
    """)
    upserted = cur.rowcount

    cur.execute(f"DELETE FROM {target_table} WHERE {pk} NOT IN (SELECT {pk} FROM {staging_table})")
    deleted = cur.rowcount

    return upserted, deleted


def import_cities(conn, path: Path) -> set:
    print(f"[1/2] Города: {path}")
    keep_ids = set()
    count = 0
    t0 = time.monotonic()

    columns_sql = ", ".join(CITIES_COLUMNS)
    with conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE staging_cities (LIKE cities INCLUDING DEFAULTS) ON COMMIT DROP")

        with cur.copy(f"COPY staging_cities ({columns_sql}) FROM STDIN") as copy:
            for row in iter_cities(path):
                copy.write_row(tuple(row[c] for c in CITIES_COLUMNS))
                keep_ids.add(row["geonameid"])
                count += 1
                if count % CITIES_PROGRESS_EVERY == 0:
                    print(f"  прочитано городов: {count:,}")

        # Защита от тихого стирания таблицы: DELETE ... NOT IN (SELECT ... FROM
        # staging) при ПУСТОЙ staging-таблице удалил бы вообще всё — например,
        # если файл битый/пустой и все строки не прошли валидацию (см.
        # iter_cities, там ошибки парсинга только логируются и пропускаются,
        # исключение не бросается). Явно отказываем импорту вместо того, чтобы
        # молча схлопнуть таблицу до нуля строк.
        if count == 0:
            raise RuntimeError(
                f"{path}: 0 валидных строк — похоже на пустой или повреждённый "
                "файл. Импорт остановлен, таблица cities не тронута."
            )

        print(f"  применяю upsert ({count:,} строк)...")
        upserted, deleted = _upsert_from_staging(cur, "staging_cities", "cities", CITIES_COLUMNS, "geonameid")

    conn.commit()
    print(
        f"  готово: upsert {upserted:,}, удалено устаревших {deleted:,}, "
        f"за {time.monotonic() - t0:.1f}с"
    )
    return keep_ids


def import_alternate_names(conn, path: Path, keep_ids: set) -> int:
    print(f"[2/2] Альтернативные названия: {path}")
    count = 0
    t0 = time.monotonic()

    columns_sql = ", ".join(ALT_NAMES_COLUMNS)
    with conn.cursor() as cur:
        cur.execute(
            "CREATE TEMP TABLE staging_alt_names (LIKE city_alternate_names INCLUDING DEFAULTS) ON COMMIT DROP"
        )

        with cur.copy(f"COPY staging_alt_names ({columns_sql}) FROM STDIN") as copy:
            for row in iter_alternate_names(path, keep_ids):
                copy.write_row(tuple(row[c] for c in ALT_NAMES_COLUMNS))
                count += 1
                if count % ALT_NAMES_MATCH_PROGRESS_EVERY == 0:
                    print(f"  прочитано альтернативных названий: {count:,}")

        # Та же защита, что и в import_cities: пустая staging-таблица не
        # должна приводить к тихому удалению всех альтернативных названий.
        if count == 0:
            raise RuntimeError(
                f"{path}: 0 подходящих строк (для {len(keep_ids)} городов) — "
                "похоже на пустой/повреждённый файл или пустой keep_ids. "
                "Импорт остановлен, таблица city_alternate_names не тронута."
            )

        print(f"  применяю upsert ({count:,} строк)...")
        upserted, deleted = _upsert_from_staging(
            cur, "staging_alt_names", "city_alternate_names", ALT_NAMES_COLUMNS, "id"
        )

    conn.commit()
    print(
        f"  готово: upsert {upserted:,}, удалено устаревших {deleted:,}, "
        f"за {time.monotonic() - t0:.1f}с"
    )
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "data_dir",
        nargs="?",
        default=str(DEFAULT_DATA_DIR),
        help=f"каталог с дампами GeoNames (по умолчанию: {DEFAULT_DATA_DIR})",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir).expanduser()
    cities_path = data_dir / CITIES_FILENAME
    alt_names_path = data_dir / ALTERNATE_NAMES_FILENAME

    for p in (cities_path, alt_names_path):
        if not p.exists():
            print(f"FATAL: файл не найден: {p}", file=sys.stderr)
            sys.exit(1)

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    dsn = os.environ.get("CITY_REPOSITORY_DSN", "")
    if not dsn:
        print("FATAL: CITY_REPOSITORY_DSN не задан (см. .env)", file=sys.stderr)
        sys.exit(1)

    print("Подключение к БД...")
    t_start = time.monotonic()
    try:
        with psycopg.connect(dsn) as conn:
            keep_ids = import_cities(conn, cities_path)
            import_alternate_names(conn, alt_names_path, keep_ids)
    except psycopg.errors.UndefinedTable as e:
        print(
            f"FATAL: таблица не найдена ({e}). "
            "Примените миграцию migrations/001_cities.sql перед импортом.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Импорт завершён успешно за {time.monotonic() - t_start:.1f}с.")


if __name__ == "__main__":
    main()
