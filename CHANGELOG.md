# Changelog

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/).
Релизов/тегов пока нет — все изменения перечислены в разделе Unreleased.

## [Unreleased]

### Added

- Справочник городов GeoNames: `migrations/001_cities.sql` (таблицы
  `cities`, `city_alternate_names`, префиксные индексы `text_pattern_ops`
  — обоснование выбора индексов в комментарии к миграции) и
  `scripts/import_geonames.py` (потоковая загрузка из `cities500.txt` +
  `alternateNamesV2.txt` через `COPY` во временную staging-таблицу, затем
  `INSERT ... ON CONFLICT DO UPDATE` + `DELETE` устаревших строк —
  идемпотентно, без `TRUNCATE`: сбой на середине импорта не оставляет
  таблицу пустой/неполной, `cities` и `city_alternate_names` коммитятся
  независимо).
- `PostgresCityRepository` — рабочая реализация поиска городов по
  префиксу с учётом альтернативных (в т.ч. исторических) названий и
  сортировкой по населению, вместо прежней заготовки.
- `docs/adr/0001-own-postgres-city-directory.md` — обоснование решения
  хранить справочник городов в собственном PostgreSQL, а не обращаться к
  внешнему геокодеру на каждый запрос автодополнения.
- `tests/test_postgres_city_repository.py` — интеграционные тесты
  `PostgresCityRepository` на реальных данных GeoNames (Москва vs
  одноимённые города в США, «Ленинград» → современное имя
  «Санкт-Петербург», поиск на латинице, пустой результат для
  несуществующего города); пропускаются без `TEST_POSTGRES_DSN`.
- `tests/test_import_geonames_idempotency.py` — идемпотентность импорта
  на синтетических данных: повторный запуск не дублирует строки,
  изменённые строки обновляются, пропавшие из дампа — удаляются
  (в т.ч. каскадно), сбой на середине импорта не стирает таблицу.
- Набор тестов, фиксирующих текущее поведение сервиса до изменений логики
  (`tests/`): golden-тест натальной карты с допуском `1e-6`, xfail на
  неполный состав точек, контрактные тесты `POST /calculate`, тест на
  работу расчёта без настроенного справочника городов.
- `requirements-dev.txt` (pytest, httpx) — отдельно от `requirements.txt`,
  чтобы не тянуть тестовые зависимости в продовый образ.
- Технический релиз сервиса как самостоятельного репозитория: `Dockerfile`
  (multi-stage под Timeweb Cloud App Platform, непривилегированный
  пользователь), `LICENSE` (полный текст AGPL-3.0), `README.md`,
  `MIGRATION_NOTES.md`, `.gitignore`, `.dockerignore`, `.env.example`.
- Адаптер справочника городов `city_repository.py` (`CityRepository`,
  `NullCityRepository`) — источник справочника выбирается через
  переменную окружения `CITY_REPOSITORY_SOURCE`.

### Changed

- Зависимости в `requirements.txt` запинены на точные версии
  (`kerykeion==5.12.8`, `pyswisseph==2.10.3.2` и остальные — актуальные
  совместимые), таргет — Python 3.11.

### Removed

- Прямая зависимость `geocoder.py` от Supabase REST — доступ к
  справочнику городов вынесен за интерфейс `CityRepository`; расчёт
  натальной карты теперь не требует БД, если координаты и таймзона
  переданы явно.

### Known issues

Зафиксированы тестами намеренно, не исправлены (логика не менялась):

- `calculator.PLANET_ATTRS` декларирует точку `Mean_Node`, которая
  фактически не считается — используемая версия kerykeion (5.12.8) не
  выставляет атрибут `mean_node` на объекте `AstrologicalSubjectFactory`.
  См. `tests/test_points_completeness.py`, `MIGRATION_NOTES.md`.
- `POST /calculate` возвращает `500 Internal Server Error`, а не
  `422 Unprocessable Entity`, для некорректных даты/времени/несуществующей
  таймзоны — входные данные не валидируются. См.
  `tests/test_api_contract.py`, `MIGRATION_NOTES.md`.
