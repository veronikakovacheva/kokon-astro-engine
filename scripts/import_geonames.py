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

Из alternateNamesV2.txt (обычно несколько сотен МБ и десятки миллионов
строк по ВСЕЙ базе GeoNames, не только по городам) берутся только записи,
относящиеся к geonameid из cities500.txt, и только языки ru/en, плюс
записи с непустым признаком исторического названия — независимо от языка
(чтобы находить города по старым именам, например "Ленинград"). Файл
читается потоково, построчно — целиком в память не загружается.

Схема — см. migrations/001_cities.sql, применить нужно заранее.
Подключение к БД — через переменную окружения CITY_REPOSITORY_DSN (.env).

Идемпотентность: импорт выполняется в одной транзакции, которая начинается
с TRUNCATE обеих таблиц и заканчивается COPY свежих данных. Это полная
замена справочника, а не добавление — повторный запуск не может создать
дубликаты, а при сбое на середине транзакция откатывается и старые данные
остаются нетронутыми.

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
    """Стримит cities500.txt и отдаёт словари в порядке CITIES_COLUMNS."""
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


def import_cities(cur, path: Path) -> set:
    print(f"[1/2] Города: {path}")
    keep_ids = set()
    count = 0
    t0 = time.monotonic()

    columns_sql = ", ".join(CITIES_COLUMNS)
    with cur.copy(f"COPY cities ({columns_sql}) FROM STDIN") as copy:
        for row in iter_cities(path):
            copy.write_row(tuple(row[c] for c in CITIES_COLUMNS))
            keep_ids.add(row["geonameid"])
            count += 1
            if count % CITIES_PROGRESS_EVERY == 0:
                print(f"  загружено городов: {count:,}")

    print(f"  готово: {count:,} городов за {time.monotonic() - t0:.1f}с")
    return keep_ids


def import_alternate_names(cur, path: Path, keep_ids: set) -> int:
    print(f"[2/2] Альтернативные названия: {path}")
    count = 0
    t0 = time.monotonic()

    columns_sql = ", ".join(ALT_NAMES_COLUMNS)
    with cur.copy(f"COPY city_alternate_names ({columns_sql}) FROM STDIN") as copy:
        for row in iter_alternate_names(path, keep_ids):
            copy.write_row(tuple(row[c] for c in ALT_NAMES_COLUMNS))
            count += 1
            if count % ALT_NAMES_MATCH_PROGRESS_EVERY == 0:
                print(f"  загружено альтернативных названий: {count:,}")

    print(f"  готово: {count:,} альтернативных названий за {time.monotonic() - t0:.1f}с")
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
            with conn.cursor() as cur:
                print("Очистка текущих данных (TRUNCATE cities, city_alternate_names)...")
                cur.execute("TRUNCATE TABLE cities, city_alternate_names")

                keep_ids = import_cities(cur, cities_path)
                import_alternate_names(cur, alt_names_path, keep_ids)

            conn.commit()
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
