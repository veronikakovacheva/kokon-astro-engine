-- Миграция 001: справочник городов (GeoNames) и альтернативные названия.
--
-- Источник данных: https://download.geonames.org/export/dump/
--   cities500.txt        -> cities
--   alternateNamesV2.txt -> city_alternate_names (только geonameid из cities,
--                           только языки ru/en, плюс исторические названия
--                           любого языка — см. scripts/import_geonames.py)
-- Лицензия данных GeoNames: CC BY 4.0, требуется атрибуция (см. README.md).
--
-- ── Выбор индексов под автодополнение по префиксу ──────────────────────────
--
-- Нужен быстрый регистронезависимый поиск "начинается с X" (LEFT-anchored
-- prefix match) для кириллицы и латиницы одновременно. Рассматривались три
-- варианта:
--
--   1. Обычный btree по name/alternate_name — не подходит: в локали, где
--      сортировка строк не побайтовая (не "C"), планировщик не может
--      использовать обычный btree-индекс для LIKE 'x%', потому что порядок
--      индекса определяется locale-специфичными правилами сравнения, а не
--      побайтовым сравнением, которое требуется для префиксного LIKE.
--   2. btree с operator class text_pattern_ops — индекс хранит и
--      сравнивает строки побайтово (как в локали "C") независимо от
--      локали базы данных, поэтому индекс по lower(name) с
--      text_pattern_ops напрямую ускоряет
--      `lower(name) LIKE lower(:q) || '%'` для любого алфавита, включая
--      кириллицу (побайтовое сравнение UTF-8 корректно сохраняет порядок
--      сравнения префиксов). Компактный индекс, дешёвый в построении и
--      обслуживании — то, что нужно для чистого префиксного поиска.
--   3. pg_trgm (триграммы, GIN) — оптимален для ПОДСТРОЧНОГО ('%x%') или
--      fuzzy/похожего поиска (similarity, опечатки), но для чистого
--      префикса избыточен: индекс существенно больше, построение и
--      обновление дороже, а выигрыша в скорости по сравнению с
--      text_pattern_ops для LEFT-anchored запроса он не даёт.
--
-- Выбор: btree + text_pattern_ops на lower(name)/lower(ascii_name) в
-- cities и на lower(alternate_name) в city_alternate_names — это именно
-- тот паттерн доступа, который нужен автодополнению (быстрый префиксный
-- поиск + ORDER BY population DESC). Если в будущем понадобится поиск с
-- опечатками или "содержит подстроку где угодно в названии" — тогда
-- стоит добавить pg_trgm (CREATE EXTENSION pg_trgm + GIN-индекс) отдельной
-- миграцией; сейчас это не требуется и не добавлено.

CREATE TABLE IF NOT EXISTS cities (
    geonameid     BIGINT PRIMARY KEY,
    name          TEXT NOT NULL,
    ascii_name    TEXT NOT NULL,
    latitude      DOUBLE PRECISION NOT NULL,
    longitude     DOUBLE PRECISION NOT NULL,
    country_code  CHAR(2),
    admin1_code   TEXT,
    population    BIGINT,
    timezone      TEXT,
    feature_code  TEXT
);

COMMENT ON TABLE cities IS
    'Города из дампа GeoNames cities500.txt. Источник: '
    'https://download.geonames.org/export/dump/, лицензия CC BY 4.0. '
    'Загружается scripts/import_geonames.py.';

CREATE TABLE IF NOT EXISTS city_alternate_names (
    id              BIGINT PRIMARY KEY,  -- alternateNameId из GeoNames (глобально уникален)
    geonameid       BIGINT NOT NULL REFERENCES cities(geonameid) ON DELETE CASCADE,
    alternate_name  TEXT NOT NULL,
    iso_language    TEXT,
    is_historic     BOOLEAN NOT NULL DEFAULT FALSE,
    is_preferred    BOOLEAN NOT NULL DEFAULT FALSE
);

COMMENT ON TABLE city_alternate_names IS
    'Альтернативные, в т.ч. исторические названия городов из '
    'alternateNamesV2.txt (только записи для городов из cities, языки '
    'ru/en + исторические любого языка). id = alternateNameId из GeoNames.';

-- Сортировка результатов автодополнения по населению (крупные города — выше).
CREATE INDEX IF NOT EXISTS idx_cities_population
    ON cities (population DESC NULLS LAST);

-- Префиксный поиск по основному и ascii-имени города.
CREATE INDEX IF NOT EXISTS idx_cities_name_prefix
    ON cities (lower(name) text_pattern_ops);
CREATE INDEX IF NOT EXISTS idx_cities_ascii_name_prefix
    ON cities (lower(ascii_name) text_pattern_ops);

-- Префиксный поиск по альтернативным названиям + обратная связь к городу.
CREATE INDEX IF NOT EXISTS idx_alt_names_geonameid
    ON city_alternate_names (geonameid);
CREATE INDEX IF NOT EXISTS idx_alt_names_prefix
    ON city_alternate_names (lower(alternate_name) text_pattern_ops);
CREATE INDEX IF NOT EXISTS idx_alt_names_language
    ON city_alternate_names (iso_language);
