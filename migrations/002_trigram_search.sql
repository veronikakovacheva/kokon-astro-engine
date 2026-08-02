-- Миграция 002: pg_trgm для поиска по подстроке (не только по префиксу).
--
-- Контекст: миграция 001 сознательно выбрала btree + text_pattern_ops
-- вместо pg_trgm, потому что тогда единственным требованием был чистый
-- префиксный поиск ("начинается с X"), для которого text_pattern_ops
-- эффективнее. Это решение не отменяется — оно ДОПОЛНЯЕТСЯ: выяснилось,
-- что для русских составных топонимов пользователи часто ищут по значимой
-- части названия, а не с начала строки — «Петербург» должен находить
-- «Санкт-Петербург», «Новгород» — «Нижний Новгород». Обычный btree (в т.ч.
-- с text_pattern_ops) физически не может ускорить LIKE '%x%' — его порядок
-- сортировки годится только для LEFT-anchored 'x%'. Единственный способ
-- ускорить поиск подстроки где угодно в названии — триграммный индекс.
-- Полное обоснование — docs/adr/0003-trigram-search-for-substring-matching.md
-- (явно ссылается на docs/adr/0001-own-postgres-city-directory.md и
-- уточняет его, а не заменяет).
--
-- Индексы миграции 001 (lower(...) text_pattern_ops) НЕ удаляются: они
-- по-прежнему быстрее для префиксного тира поиска (см. city_repository.py:
-- сначала префиксные совпадения, затем — по подстроке через индексы ниже).

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_cities_name_trgm
    ON cities USING GIN (lower(name) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_cities_ascii_name_trgm
    ON cities USING GIN (lower(ascii_name) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_alt_names_trgm
    ON city_alternate_names USING GIN (lower(alternate_name) gin_trgm_ops);
