# База Orthofill (`orthofill.db`), версия схемы 2

Описание для переноса программы на другой язык (C++/Rust): данные и проверки
лежат здесь и в `tests/cases/*.json`, а не в коде Python.
Версия схемы — `PRAGMA user_version` (0.1 — 1, 0.2 — 2). Даты — ISO 8601
(`2026-10-21T14:39:36`). JSON — только простые списки и строки.

## Пресеты

**presets** — тип карточки («Активация», «Консультация»).

| Столбец | Смысл |
|---|---|
| id | номер пресета |
| name | имя, уникальное («order», «order (2)») |
| source, source_sha256 | xlsx, из которого последний раз импортирован, и его хэш |
| imported_at, created_at | даты |
| dirty | 1 — есть эталоны/слова, которых нет в последнем выгруженном xlsx |

**preset_items** — пункты пресета в порядке вывода.

| Столбец | Смысл |
|---|---|
| preset_id, pos | пресет и порядок (как строки в xlsx) |
| code, text | код (`4`, `4b`, `4b7`) и текст пункта |
| level | 1 — раздел, 2 — группа или отдельный пункт, 3 — вариант |
| parent | код родителя (`4b` для `4b7`, `4` для `4b`) |
| orphan | 1 — вариант без своей группы, считается пунктом раздела (`4h1`) |
| method | группа: способ выбора варианта — ключ из списка ниже |
| when_ | отдельный пункт: `always` / `mentioned` |
| default_code | группа: код варианта, если врач не написал |
| words_json | дополнительные слова упоминания, JSON-список строк |

Способы выбора (`method`), подписи — `orthofill/methods.py`:
`words` (по словам записи), `system`, `stage`, `mucosa`, `hygiene`, `bracket`,
`relation`, `wire`, `ligature`, `binding`, `elastics`, `adjust`, `dynamics`, `visit`.

Пустые `method`/`when_` угадываются при импорте (`engine.guess_settings`):
способ — по тексту группы; `always` — если пункт есть больше чем в половине
эталонов пресета (или эталонов нет).

**reference_cases / reference_lines** — эталоны «запись → идеальный протокол».
`reference_cases(preset_id, pos, case_id, raw)`;
`reference_lines(preset_id, case_id, pos, code, text)` — строки протокола по
порядку; `code` пустой — свой текст врача.

**dictionary** — слова врача: `(preset_id, word)` → `item_text` (привязка к тексту
пункта, `code` — подсказка), `added`, `hits` (сколько раз сработало).

**imports / exports** — журнал импортов и выгрузок xlsx.

## Журнал (с 0.1)

**entries** — каждая сформированная запись: `raw`, `generated`, предупреждения,
значения по умолчанию, `sha256` пресета, что скопировано, номер эталона,
`preset_id` (с версии 2). **settings** — ключ/значение (`preset_id`,
`diagnostics`, `topmost`, `last_file` из 0.1). **classifier_snapshots** —
снимки классификаторов 0.1.
