-- Небольшая выборка РЕАЛЬНЫХ данных GeoNames (не синтетика) для тестов
-- PostgresCityRepository — все "Moscow"/"Saint Petersburg" записи из
-- cities500.txt плюс их альтернативные названия из alternateNamesV2.txt
-- (ru/en + исторические), отобранные тем же фильтром, что и в
-- scripts/import_geonames.py.
--
-- Источник: https://download.geonames.org/export/dump/, лицензия CC BY 4.0
-- (см. README.md, раздел «Импорт справочника городов»).
--
-- Специально включает: Moscow, RU (столица, geonameid 524901) и четыре
-- американских тёзки (TN/ME/PA/ID) — чтобы тест на поиск "Москва" мог
-- проверить, что ранжирование по населению выбирает российскую столицу, а
-- не одноимённый город в США; Saint Petersburg, RU (geonameid 498817) с
-- историческим альтернативным именем "Ленинград" (ru, isHistoric=1) — чтобы
-- проверить, что поиск по историческому названию возвращает современное имя,
-- и с ru-именем "Санкт-Петербург" не с начала строки — для поиска по
-- подстроке ("Петербург"); и Vozhd' Proletariata, RU (geonameid 471247,
-- население 594, feature_code PPL) — маленький посёлок, отобранный тем же
-- фильтром по типу населённого пункта, что и в scripts/import_geonames.py
-- (см. docs/adr/0002-import-filters-by-place-type-not-size.md), чтобы
-- проверить, что точный поиск находит его наравне со столицами.

TRUNCATE TABLE cities, city_alternate_names;

INSERT INTO public.cities VALUES (498817, 'Saint Petersburg', 'Saint Petersburg', 59.93863, 30.31413, 'RU', '66', 5351935, 'Europe/Moscow', 'PPLA');
INSERT INTO public.cities VALUES (524901, 'Moscow', 'Moscow', 55.75204, 37.61781, 'RU', '48', 10381222, 'Europe/Moscow', 'PPLC');
INSERT INTO public.cities VALUES (4642988, 'Moscow', 'Moscow', 35.06203, -89.40396, 'US', 'TN', 532, 'America/Chicago', 'PPL');
INSERT INTO public.cities VALUES (4972660, 'Moscow', 'Moscow', 45.07061, -69.89117, 'US', 'ME', 600, 'America/New_York', 'PPL');
INSERT INTO public.cities VALUES (5202009, 'Moscow', 'Moscow', 41.33675, -75.51852, 'US', 'PA', 1960, 'America/New_York', 'PPL');
INSERT INTO public.cities VALUES (5601538, 'Moscow', 'Moscow', 46.73239, -117.00017, 'US', 'ID', 25060, 'America/Los_Angeles', 'PPLA2');
INSERT INTO public.cities VALUES (471247, 'Vozhd’ Proletariata', 'Vozhd'' Proletariata', 55.43797, 39.30419, 'RU', '47', 594, 'Europe/Moscow', 'PPL');

INSERT INTO public.city_alternate_names VALUES (300633, 498817, 'Leningrad', 'en', true, false);
INSERT INTO public.city_alternate_names VALUES (300635, 498817, 'Petrogrado', 'es', true, false);
INSERT INTO public.city_alternate_names VALUES (300636, 498817, 'Petrograd', 'en', true, false);
INSERT INTO public.city_alternate_names VALUES (300637, 498817, 'Peterburg', 'en', false, false);
INSERT INTO public.city_alternate_names VALUES (300638, 498817, 'Petersburg', 'en', false, false);
INSERT INTO public.city_alternate_names VALUES (1597204, 498817, 'Saint Petersburg', 'en', false, false);
INSERT INTO public.city_alternate_names VALUES (1614553, 498817, 'Leningrado', 'es', true, false);
INSERT INTO public.city_alternate_names VALUES (1614554, 498817, 'Leningrado', 'eo', true, false);
INSERT INTO public.city_alternate_names VALUES (2181407, 498817, 'Ленинград', 'ru', true, false);
INSERT INTO public.city_alternate_names VALUES (2417766, 498817, 'Санкт-Петербург', 'ru', false, true);
INSERT INTO public.city_alternate_names VALUES (2417767, 498817, 'St. Petersburg', 'en', false, false);
INSERT INTO public.city_alternate_names VALUES (2417768, 498817, 'St.-Petersburg', 'en', false, false);
INSERT INTO public.city_alternate_names VALUES (2417769, 498817, 'Петербург', 'ru', false, false);
INSERT INTO public.city_alternate_names VALUES (2426909, 498817, 'СПб', 'ru', false, false);
INSERT INTO public.city_alternate_names VALUES (2426910, 498817, 'Питер', 'ru', false, false);
INSERT INTO public.city_alternate_names VALUES (2432652, 498817, 'Петроград', 'ru', true, false);
INSERT INTO public.city_alternate_names VALUES (5974474, 498817, 'Petrogrado', NULL, true, false);
INSERT INTO public.city_alternate_names VALUES (5974475, 498817, 'Petrograd', NULL, true, false);
INSERT INTO public.city_alternate_names VALUES (5974478, 498817, 'Leningrad', NULL, true, false);
INSERT INTO public.city_alternate_names VALUES (9858113, 498817, 'Leningrad', 'fi', true, false);
INSERT INTO public.city_alternate_names VALUES (10379819, 498817, 'Petrapilis', 'lt', true, false);
INSERT INTO public.city_alternate_names VALUES (13288312, 498817, 'St Petersburg', 'en', false, false);
INSERT INTO public.city_alternate_names VALUES (13634195, 498817, 'Petrograd', 'de', true, false);
INSERT INTO public.city_alternate_names VALUES (13634196, 498817, 'Leningrad', 'de', true, false);
INSERT INTO public.city_alternate_names VALUES (19253466, 498817, 'Lenjingrad', 'hr', true, false);
INSERT INTO public.city_alternate_names VALUES (19253467, 498817, 'Petrograd', 'hr', true, false);
INSERT INTO public.city_alternate_names VALUES (1590979, 524901, 'Moscow', 'en', false, true);
INSERT INTO public.city_alternate_names VALUES (2729045, 524901, 'Москва', 'ru', false, true);
INSERT INTO public.city_alternate_names VALUES (13858381, 524901, 'Moskva', 'az', true, true);
INSERT INTO public.city_alternate_names VALUES (3044885, 4642988, 'Город Москва', 'ru', false, false);
INSERT INTO public.city_alternate_names VALUES (18473387, 4642988, 'Moscow', 'en', false, false);
INSERT INTO public.city_alternate_names VALUES (3045572, 4972660, 'Город Москва', 'ru', false, false);
INSERT INTO public.city_alternate_names VALUES (18560420, 4972660, 'Moscow', 'en', false, false);
INSERT INTO public.city_alternate_names VALUES (3046259, 5202009, 'Москва', 'ru', false, false);
INSERT INTO public.city_alternate_names VALUES (12992664, 5202009, 'Moscow', 'en', false, true);
INSERT INTO public.city_alternate_names VALUES (3046706, 5601538, 'Москва', 'ru', false, false);
INSERT INTO public.city_alternate_names VALUES (8706818, 5601538, 'Москоу', 'ru', false, false);
INSERT INTO public.city_alternate_names VALUES (13133715, 5601538, 'Moscow', 'en', false, true);
INSERT INTO public.city_alternate_names VALUES (1747373, 471247, 'Vozhd'' Proletariata', 'en', false, false);
INSERT INTO public.city_alternate_names VALUES (1747374, 471247, 'Вождь Пролетариата', 'ru', false, false);
