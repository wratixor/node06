# P04a: read-only проверка Git-корней

Реализован локальный preflight, первый этап P04. Он проверяет manifest и данные
из конкретного коммита, формирует детерминированный кандидат и **не пишет в БД**.
Это не подключение источника к серверу, не подтверждение владения репозиторием,
не HTTP endpoint и не завершённый importer. Нельзя публиковать результат только
на основании `site_id` или успешного preflight.

## Контракт и ограничения

Структурная JSON Schema:
[schemas/root-manifest-v1.schema.json](schemas/root-manifest-v1.schema.json).
Её источник — `RootManifest` в `root_import.py`, test проверяет отсутствие drift.
Дополнительные семантические проверки графа/путей выполняются кодом, не одной
JSON Schema. Будущие расширения manifest должны сохранять версию/совместимость
или явно вводить новую версию; неизвестные поля сейчас отклоняются.

Manifest `node06-roots.json` находится в корне Git-снимка; CLI может выбрать
другой безопасный относительный путь. `content_directory` пока строго
`site-content`. Все `file` считаются относительно этой директории. Копия upstream
`content/` и неуказанные файлы не импортируются и не исполняются.

- `schema_version`: integer 1; `site_id`: ожидаемый `s_` + 32 lowercase hex.
- `points`: до 100 элементов `{id,file,lang}`. ID: 1–61 lowercase ASCII
  букв/цифр/дефисов, начинается с буквы/цифры; `welcome` зарезервирован.
- `welcome`: необязательный `{file,mode:"git",lang?}`, lang по умолчанию `und`.
  Он разрешается в существующий site ID, а не новую копию welcome.
- `lang`: ограниченная синтаксическая метка языка, не механизм локализации и не
  проверка IANA-каталога. Текст может быть на любом языке; автоматических пар нет.
- `source_proof`: необязательный 64-hex слот для будущего challenge; этот этап
  **не выдаёт и не проверяет** доказательство. В отчёт proof/body не выводятся.
- Пути ASCII, относительные, до 256 символов/8 компонентов, без скрытых/dot/empty
  компонентов и обратных слешей; только `.md`. Один файл/ID не повторяется.
- Manifest до 16 KiB, Markdown до 32 KiB на файл, source до 1 MiB с manifest,
  до 16 уникальных исходящих point-ссылок на точку. Это текущие ceilings preflight,
  не измеренная производственная ёмкость и не утверждённые коммерческие тарифы.

Git mode 100644/100755 читается как данные, execute-bit ничего не запускает.
Symlink/submodule/non-blob, Git LFS pointer, неверный UTF-8, NUL/control-текст,
превышение бюджета и traversal отклоняются. Ошибка содержит стабильный код,
относительный файл и строку при наличии, без исходного текста/секретов.

## Markdown и ссылки первого этапа

Сохраняется исходный Markdown; preflight не рендерит HTML. Поддерживаемая часть
point-ссылок — inline `[label](md://local/id)` и `[label](md://point/global_id)`.
Текст в fenced/inline code не становится связями. Неоднозначные/неподдерживаемые
`md://` формы, повторы, self-ссылки, raw HTML/изображения вне code и опасные схемы
inline URL отклоняются. Полный Markdown renderer с безопасным HTML boundary и
всеми syntax fixtures нужен перед публичным импортом; старый статический builder
не становится доверенным renderer для чужого текста автоматически.

Local ID превращается в `r_<site_uuid32>_<id>`, `local/welcome` — в site ID.
Локальные point-связи взаимны; внешняя ссылка не требует править чужой файл.
Внешние targets разрешаются только по переданному доверенному индексу публичных
revision IDs. Они фиксируются в кандидате; изменение индекса меняет digest.
Исторические citation pins и проверка target/ACL при accept — следующий этап.
Нельзя подставить собственный namespaced target через `point/` вместо `local/`.

Одинокая точка разрешена с предупреждением, не удаляется автоматически.
Сортировка отчёта стабильна. Смысловой digest включает ID/lang/body/declared refs/
external pins, но не путь файла, commit или временные метки: переименование файла
не меняет идентичность/смысл. Candidate digest фиксирует commit и manifest как
снимок для будущего review; он не является подписью/разрешением на публикацию.

## Как проверить свой источник

Нужны зависимости backend и Git >=2.46. Пример готов в
[examples/root-source](../examples/root-source/node06-roots.json): скопируйте его
содержимое в свой репозиторий, замените демонстрационный site ID, сделайте commit.
Для локальной проверки из checkout NODE06:

```bash
.venv/bin/python -m node06_service.root_preflight \
  --repo /path/to/your/clone \
  --commit FULL_40_CHARACTER_COMMIT_SHA \
  --site-id s_YOUR_32_HEX_SITE_ID
```

Это placeholders, не рабочие адреса/ID. Установленный wheel также предоставляет
команду `node06-root-preflight`. Схема доступна через `--schema`.

Git metadata должна принадлежать вашему доверенному локальному clone, который
вы создали сами; не запускайте CLI от root на присланном чужом `.git` каталоге.
Содержимое корней в commit считается недоверенным. CLI читает `ls-tree`/`cat-file`
по SHA, без checkout/build/hooks/fetch, с timeout, disabled fsmonitor/replace refs
и `GIT_NO_LAZY_FETCH=1`. Не хватает объектов — отказ, не скрытая загрузка.
См. [Git environment](https://git-scm.com/docs/git).
Старые Git отклоняются до чтения объектов; рабочие незакоммиченные файлы
не участвуют и не меняются. Сборка/preview чужих workflows не выполняются.

Для внешних point-ссылок можно добавить `--public-revisions /path/to/index.json`:

```json
{"all-sites": "v_00000000000000000000000000000000"}
```

Индекс в этом локальном инструменте предоставляет вызывающий оператор; файл не
доказывает публичность/доступность целей. В серверном accept индекс должен
строиться из канонических публичных данных и перепроверяться транзакционно.
Текущие 51 core roots ещё не импортированы в БД: не выдумывать им DB revision IDs
из timestamps/хешей фронтенда ради прохождения проверки.

Вывод — JSON с commit/digests, ID/lang/paths/links/pins и предупреждениями;
`writes_performed=false`, `source_ownership_verified=false`. Он не содержит
Markdown body или source proof. Нет соединений с БД и новых HTTP маршрутов.

## Что дальше

P04b должен добавить authenticated owner source registration и repo challenge,
фиксированный безопасный GitHub fetch конкретного commit, сохранённый приватный
preview/diff и атомарный accept с повторной проверкой owner/source/revisions.
Нужны core projection/revisions, provenance edge claims и безопасное retirement;
не выкладывать Git welcome поверх UI welcome без явного перехода источника.
Только затем подключать источники к `/sites/`, public graph и профилю стартовых
корней/облака. Полный контракт: [ROOT-IMPORT-V1](ROOT-IMPORT-V1.md).
Этот пакет не меняет действующий сервер, модель влияния или авторизацию.

## Проверено в P04a

Полный локальный suite с disposable PostgreSQL: **142 passed**, в том числе
46 новых preflight/Git-объектных fixtures. Ruff/format, статическая сборка 51
корня, P00 protocol и diff/link checks прошли. Wheel собран и установлен в
изолированный target; его CLI/schema проверены на committed bilingual примере
из examples, с совпадением опубликованной JSON Schema и чистым Git status.
Рабочая БД/сервер, регистрация источника и public imports не изменялись.
