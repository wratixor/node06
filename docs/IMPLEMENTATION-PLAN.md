# NODE06 — сервис общей вики для независимых сайтов

Статус на 24 октября 2026: реализованы аккаунты/восстановление, сайты и главные,
операторская Git-публикация, hosted/full iframe/public bridge, редактор точек,
версии/голосования/уведомления, T1 и социальная геометрия, публичные профили,
блокировки авторов и доверенный выбор личных тегов для внешних черновиков.
Личная лента создания и компактная цветная диаграмма также реализованы:
[CREATION-FEED-V1](CREATION-FEED-V1.md). Готовность исходников не доказывает деплой.
Scoped authenticated embed, внешний inline edit своих точек, self-service Git,
баны/удаление и синхронизация ещё впереди. Роли, жалобы и скрытие реализованы:
[MODERATION-V1](MODERATION-V1.md). Последние решения:
[MODERATION-PLAN](MODERATION-PLAN.md). Исторические записи Progress ниже сохраняют
состояние на свою дату; актуальные контракты и последние пакеты имеют приоритет.
Создан: 12 сентября 2026. Пересобран: 13 сентября 2026, Europe/Moscow.
Редакция 2: общая сеть сайтов, bridge + full embed + hosted frontend + GitHub roots.
Владелец продуктовых решений: Wratixor.
Этот документ — основной план продолжения; [API-V1.md](API-V1.md) — актуализированный
проект контракта HTTP; [EMBED-V1.md](EMBED-V1.md) описывает встраивание,
[ROOT-IMPORT-V1.md](ROOT-IMPORT-V1.md) — GitHub/Markdown импорт. Пометки **Решено**, **Предложение** и **Открыто** различают требования
владельца, инженерные рекомендации и ещё не принятые решения. Числа ниже —
стартовые предложения для измерений, а не незаметно утверждённые правила.

## 1. Результат и принятые решения

NODE06 — переосмысленный движок концептов, из которого делаем полноценный
сервис для независимых сайтов, прежде всего Neocities Free. Сайт NODE06 —
демонстрация сервиса и его участник. Все подключённые сайты, обычные мысли,
публикации и открытый лор находятся **в одном общем пространстве смыслов**,
с общей БД, пользователями, графом и расчётом влияния **внутри экземпляра сервиса**.
Уточнение 22.10: независимые экземпляры и ссылки между ними — отдельный сетевой
уровень; собственные root-наборы и входы описаны в
[ENTRANCES-ROOTS-NETWORK.md](ENTRANCES-ROOTS-NETWORK.md).

**Решено владельцем 13.09.2026:**

- На Амстердаме размещаются backend и полноценный фронтенд из того же репозитория.
  Это hosted-версия одного продукта, не отдельная копия контента/базы.
- Поддерживаются оба режима: маленький iframe-посредник для интерфейса на чужом
  сайте и iframe всей вики, как встраиваемый видеоплеер. Supporter не нужен
  как архитектурная предпосылка. Фактическую совместимость проверяем прототипом.
- Каждый подключённый сайт получает точку `s_<uuid>` с собственной приветственной
  страницей. Без явной ссылки на другую точку встраивание открывает её по умолчанию.
- Точка сайта связана с общим Git-owned корнем `all-sites` («Все сайты»).
  Эта связь обеспечивает общую навигацию, не выдаёт влияние или полномочия.
- Каждый сайт настраивает приветствие и оформление; CSS остаётся у владельца,
  с разными механизмами для локального UI и внешнего iframe.
- Добавляется путь подключения через GitHub fork: дополнительные root Markdown
  принадлежат репозиторию сайта и импортируются в общий граф с отдельными ID.
- Будущий `wiki.geno-dice.com` — ещё одна точка входа в **тот же граф** открытого
  лора. Владелец явно отклонил отдельное изолированное пространство канона.
- Позже добавить простую ссылку поддержки на существующий кошелёк Geno-Dice.
  Тарифы/квоты вводить по росту нагрузки и стоимости сервера, без покупки влияния.
- Базовый характер сохраняется: карта первична, точки не требуют категорий и
  заголовков, новые мысли связываются с существующими, RU/EN — разные точки.
- Пользователи общие для всех сайтов; сайт и аккаунт — разные сущности.
- Автор может править свои точки, владелец сайта — своё приветствие. Поддержавшие
  изменённую точку получают уведомление. Географическая модерация — на будущее.
- При написании автор выбирает слово/фразу и через быстрый поиск связывает её
  с конкретным смыслом, в том числе лорным; можно оставить обычным текстом.
- Эта часть фиксирует исходное планирование 13.09. Текущее состояние реализации
  смотреть в Progress: сервер, public bridge, операторская публикация Git,
  пользовательские точки и голосование реализованы. Самостоятельный importer
  и межсерверная синхронизация остаются следующими этапами.

Авторитет канонических текстов определяется **правами редактирования и
происхождением**, а не отдельным миром и не голосованием. Обычная пользовательская
точка может ссылаться на лор и обсуждать его. Это не даёт её автору права менять
канонический Markdown. Общий граф не требует публиковать скрытый лор.

Источники правды: Git — core roots и opt-in site roots; БД — социальные точки,
связи, сайт-владелец, редакторские настройки, авторизация и события. Один активный
режим источника приветствия: UI редактор **или** Git, без двух конкурирующих
писателей. Frontend mirrors ничего из этого не дублируют.

Первый публичный результат: два независимых сайта входят в один граф со своих
приветствий; публикация на A видна по ссылке на B и hosted-версии, один голос
не дублируется между сайтами. Оба способа встраивания работают на реальном Free.
Социальная геометрия v1 теперь реализована поверх сохранённых событий и T1:
нормированные пользовательские координаты, подписки и противоположные пары
для блокировок. Контракт: SOCIAL-GEOMETRY-V1; исходный код и production-публикация
проверяются отдельно.

## 2. Проверенная исходная точка

Исследованный исходный commit: `daffcee7ba3135368c905969ae0a4caa8119ff19`.
Origin: `git@github.com:wratixor/node06.git`. Это выбранный владельцем проект,
не считать его зеркалом только из-за личного namespace. На старте checkout чистый,
`main`, интеграционная ветка `origin/main`. Fetch GitHub по SSH в сессии
завершился DNS-ошибкой; последующая HTTPS `ls-remote` подтвердила тот же HEAD/main
и отсутствие `develop` на момент проверки.

| Область | Реально существует | Последствие для реализации |
|---|---|---|
| Сборка | Python stdlib `build.py`, без менеджера пакетов | Статическая сборка должна и дальше работать без установки backend |
| Контент | 23 точки: 11 EN, 12 RU; 35 неориентированных рёбер | Зафиксировать ID и исходные связи, не пересоздавать корни |
| Скрытая находка | `content/ru/welcome.md`, степень 0 | Не удалять как ошибку связности; намеренно отдельная точка |
| Root graph | `md://`, проверка существования и взаимности | API добавляет динамику, не переписывает Markdown |
| Индекс | `dist/data/points.json`: массив, `html`, `preview`, `lang`, `links`, даты, координаты | Изменять через совместимое расширение либо новую версию |
| Даты | `created_at` и активность из filesystem mtime | Новый checkout способен изменить историю всех корней |
| Карта | Один `static/site.js`, SVG, глубина 2, вращение/масштаб | Сначала выделить слой данных, сохранить управление |
| Геометрия | Версионированный Git-owned `content/root-coordinates-v1.json` задаёт шесть скрытых системных Древних-якорей и шесть их фиксированных вкладов для каждого root; сборка выводит начальные координаты и проверяет схему | Это исходная смысловая раскладка, не социальные измерения; Древние и подписи осей не видны на публичной карте |
| Размер | Радиус от `degree`; цвет сфер общий | Не называть текущий размер влиянием |
| UI | READ/EXPLORE/FEED, справа/снизу/поверх, deep links и history | Все режимы входят в регрессионную матрицу |
| Backend | Только документ API; кода, миграций и backend-тестов нет | Нельзя ссылаться на уже существующие API/CLI команды |
| Deploy | GitHub Actions строит `dist/`, на `main` публикует в Neocities | Feature push не равен публикации сайта; merge в main запускает её |

Локальная сборка исходной модели прошла. Опубликованное `/en/` просмотрено в
браузере; неправильный адрес ссылки NODE06 подтверждён. Изменение этой ссылки
и кликабельного H1 выполнено отдельным небольшим изменением в этой сессии.

### Замеченные технические пробелы

1. В исходной ревизии README говорил об отдельном репозитории бэкенда, API предлагал `backend/`.
   Этот план уточняет: один Git-репозиторий, два независимых способа доставки.
2. `site.js` предполагает наличие всех точек в памяти, готового `html` и `lang`;
   API этого не гарантирует. Нужен адаптер, а не подмена URL одного fetch.
3. RU/EN-фильтр при выборе центра, история и ссылки из `render_inline` расходятся
   с уже существующими межъязыковыми рёбрами. Язык UI не должен менять ID точки
   или запрещать её открыть. Смена языка текста не порождает авто-перевод.
4. `md://` допускает только `[a-z0-9-]+`, будущие `p_...` ему не соответствуют.
   Разделить правила root ID и dynamic ID; общий парсер ссылок должен знать оба.
5. Сейчас root validator не запрещает self-link и повтор одной ссылки явно.
   Для нового контракта зафиксировать одинаковую политику проверки.
6. Ошибка первого fetch и отказ `localStorage` способны сорвать запуск UI.
7. `coordinates=null` сейчас превращается в `[1,1,1,1,1,1]`; совпадающие
   направления дают наложение. Нужна отдельная раскладка неопределённых точек.
8. Корневые deep links ведут через redirect в JS-поле: без JS нет полного
   чтения текста. Для инди-веба полезен статический читаемый permalink.
9. SVG-точки выбираются указателем, но не имеют полноценного фокуса/Enter;
   перерисовка происходит на каждый pointermove. Нужны клавиатура, текстовый
   список соседей, requestAnimationFrame и проверка touch/scroll.
10. `scripts/publish.sh` делает `git add -A` и push текущей ветки без её защиты;
    `docs/FIRST-PUSH.md` содержит одноразовые устаревшие шаги amend/force push.
    Не исполнять их при продолжении. Обновить в этапе подготовки.

## 3. Основной транспорт: внешний iframe

У NODE06 Free 12 и 13 сентября 2026 проверен HTTP CSP:

```text
connect-src 'self' data: blob:;
form-action 'self';
frame-src *;
```

Прямой fetch с Neocities к внешнему API запрещён, внешняя HTML-страница в iframe
разрешена текущим `frame-src`. Она загружается по HTTPS со своего origin и
обращается к своему API. Это обычное cross-origin встраивание, не отключение CSP.
Весь код статического/hosted UI принадлежит одному репозиторию.

**Решено:** основной путь — собственный iframe bridge, плюс full embed и
hosted-вход. Предыдущее предложение Supporter как основного пути отменено.
CORS-proxy третьих лиц, JSONP, исполняемые API-ответы и CSP meta bypass не нужны.
`srcdoc`/about:blank не заменяют внешний документ с собственным origin.

Точный протокол, origin-проверки, версии, вход и темы — [EMBED-V1.md](EMBED-V1.md).
P00 сначала доказывает в браузере read/write roundtrip с применённым настоящим
CSP на двух локальных origins; затем отдельный test-page на Neocities и сервере
проверяет реальную связку после разрешения на test deployment. Локальная
симуляция не выдаётся за production smoke.

Full embed может работать read-only даже без parent JS. Bridge требует локальный
loader/SDK и локальный UI. При отказе iframe — понятное сообщение и обычная
ссылка «Открыть вики» на hosted-версию; root read-only fallback сохраняется.
Поддержка «любого сайта» означает HTTPS-сайты, разрешающие внешний iframe;
чужую CSP, запрет iframe или отсутствие JS сервис не может отменить.

Нельзя требовать third-party cookies для чтения/записи: вход через trusted
hosted top-level/popup, scoped session внутри iframe, без выдачи пароля/глобальной
сессии JavaScript владельца сайта. Нужно проверить блокировку popup, storage
partitioning, reload/logout и отказ cookies в Chromium/Firefox/Safari.

Источники: [iframe](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/iframe),
[postMessage](https://developer.mozilla.org/en-US/docs/Web/API/Window/postMessage),
[same-origin](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Same-origin_policy).
Это подтверждение возможностей браузера; интеграция NODE06 пока не реализована.

## 4. Как изменился замысел движка

Общая документация остаётся источником лора и истории решений. Текущий
прикладной контракт ниже учитывает явные уточнения владельца, не возвращает
старые схемы между строк.

| Ранее | Теперь | Инвариант |
|---|---|---|
| NODE06 как один эксперимент | NODE06 демонстрирует сервис многих сайтов | Один shared graph и DB, не копия на каждый iframe |
| Server только JSON | API + bridge HTML + full frontend в Амстердаме | Wagtail/кошелёк отдельные приложения |
| Supporter или невыбранный transport | Два iframe режима — основная поставка | Реальный Free smoke обязателен |
| Один root tree | Core tree + проверенные site Git imports | Namespace/provenance, стабильные ID |
| Вход в RU/EN-раздел | Общий граф; конкретная точка сайта — default | Язык интерфейса не меняет identity |
| Отдельный мир лора | Лор в общем пространстве, отдельный вход | Редакционные права и скрытые исходники не становятся общими |
| Старые обязательные теги/категории | Untyped point body + links | Сайт и импорт — metadata происхождения/управления |
| Только root/user origin | root/user/site origin | `s_` — site point, `r_` — namespaced Git root |
| Связи только при создании | Автор может менять текст и исходящие ссылки своей точки; системные/import связи имеют происхождение | Нет права соединять две произвольные чужие точки |
| F–S и legacy self-anchors | Отдельные будущие ADR | Не отменять и не внедрять тайно |
| Влияние отдельного экземпляра | N active людей на весь shared graph | Количество сайтов/форков/встраиваний не добавляет массу |
| Монетизация вне задачи | Простая ссылка кошелька, позже resource tiers | Оплата не меняет голос, канон или право на чужие данные |

Открытая вики лора будет иметь site point и reviewed Git roots в этой же модели.
Ссылка `all-sites↔s_lore`, внешние discussion points и соседство допустимы;
редактировать авторские roots можно только через их разрешённый источник.

## 5. Архитектура, точки сайтов и владение

```text
Core Git roots -----------+                    Neocities A: local UI + CSS
Site forks (MD only) -----+--> validated import       | postMessage
                         |                           v
                         +--> shared PostgreSQL <--- API <-- bridge iframe
                         |                           ^
                         |                     full iframe on site B
                         |                           ^
                         +--> versioned snapshots --> hosted full wiki
                                                     + future wiki.geno-dice.com
```

Один репозиторий, один frontend source/renderer, три оболочки: standalone,
full embed, SDK + local renderer. Один backend и одна PostgreSQL DB. Nginx
раздаёт versioned static assets, bridge/embed HTML и проксирует same-origin API.
Separate origins для management/login и embed предпочтительны: недоверенное
оформление/embedding не расширяют доступ к аккаунту владельца.

Стек-предложение: Python 3.12 baseline, FastAPI/Pydantic2, SQLAlchemy2 sync,
psycopg3, Alembic, PostgreSQL, Argon2id, Uvicorn. Проверить совместимые версии
и lock в P01; не смешивать blocking SQL/hash с `async def`. Чистая математика
без ORM, одна отдельная snapshot CLI/job вместо расчёта в web handlers.

```text
backend/app/
  api/{auth,points,users,feed,sites,imports,meta}.py
  domain/{trust,mass,geometry,quotas}.py
  services/{site_claims,root_sync,events,snapshots,moderation,embed_sessions}.py
  models/ schemas/ cli.py
backend/alembic/versions/ backend/tests/
static/                        # общие UI/renderer/safe-text/point-store
  embed/                       # минимальная bridge страница и iframe shell
  sdk/                         # versioned loader + theme adapter
content/                       # существующие core roots
site-content/                  # opt-in roots владельца fork; не весь content/
node06.site.example.json        # шаблон, не действующая регистрация
build.py                       # Neocities/hosted/embed artifacts из одной базы
```

### Точка сайта и его приветствие

`sites.id = points.id = s_<uuid32>`: это одна публичная точка и одна служебная
site registration, не две точки. `home_point_id` фиксирован на этом ID в MVP;
`?p=`/встроенная deep link может открыть другую public point. Site point body
— приветствие, optional preview/title сайта живут в site settings и не делают
поле title обязательным у всех concepts. Темы/раскладка — настройки оболочки.

На регистрации создаётся pending site без public directory spam. После
подтверждения владения в одной транзакции появляются site point, active site,
системная симметричная связь `s_id↔all-sites`, событие и готовая embed config.
Повтор verify не создаёт дублей. Все сайты проходят тот же протокол, включая
NODE06 и будущую lore wiki; bootstrap core `all-sites` не создаётся посетителем.

**Предложение проверки владения:** уникальный challenge-файл по фиксированному
пути на claimed HTTPS origin; для Neocities это обычный допустимый `.txt` файл.
Сервис запрашивает только этот фиксированный путь с лимитами и SSRF-защитой,
а не произвольный URL. Full contract — ROOT-IMPORT-V1. Public `site_id` не ключ.
MVP один verified primary origin на site, coowners/admins имеют отдельные роли.
Custom domain/alias добавляется после отдельного proof; не даёт вторую точку.

Onboarding: создать аккаунт на trusted hosted domain → заявить origin →
разместить proof → настроить приветствие/тему → выбрать full iframe или local UI
SDK → скопировать snippet → выполнить диагностику. GitHub fork — дополнительный
путь, не обязательное условие использования сервиса.

**Права (с уточнением владельца 23.10):** site owner меняет своё приветствие,
источники и theme в рамках их source authority; автор напрямую меняет свою
не-Git точку только без активных подписчиков, иначе — через голосование.
Все Git-owned точки защищены от предложений сообщества; accepted Git update
напрямую меняет текст и автоматически переносит активную поддержку с записью
истории переноса и публичного ченжлога; operator осуществляет общую abuse moderation. Владение
сайтом не даёт контроля над соседними точками и чужими реакциями. Сайт может
курировать отображение своей оболочки без удаления объектов общего графа.
Уход/блокировка сайта не удаляет чужие точки; каталог хранит inactive tombstone,
а imports/связи меняются по отдельному lifecycle. Домен не переуступается новому
владельцу аккаунта без reverify и явной передачи авторских объектов.

`all-sites` быстро становится hub: вид должен иметь directory pagination,
поиск и bounded field. Не загружать всех зарегистрированных соседей и их depth2
на открытие каждого сайта. Site→all-sites — directory edge; в default локальном
виде сам каталог виден, его массовое расширение идёт по запросу с cursor.
Это правило раскрытия UI/API, а не отдельное пространство смыслов.

## 6. Данные и синхронизация Git

### Источники и стабильные ID

Core roots сохраняют существующие slug IDs; новый core ID `all-sites` будет
добавлен отдельной задачей. Sites: `s_<uuid32>`, users: `u_<uuid32>`, authored
points: `p_<uuid32>`. Site Git roots: `r_<site_uuid32>_<stable_local_id>`.
Тип происхождения не превращает мысль в жёсткую смысловую категорию.

`namespace=core` или `site_id` — происхождение/владение и защита имён,
**не фильтр видимости и не отдельный граф**. Одинаковые слова/slug на двух
сайтах могут быть двумя самостоятельными связанными точками. Переименование
файла не меняет manifest stable ID. Не объединять roots по одинаковому body.

Core Markdown остаётся в основном Git. Site roots — в подключённом GitHub fork
или другом public GitHub repository того же формата. Не импортировать всю копию
core `content/` из форка, иначе every fork размножит исходный мир. Import opt-in
только manifest path и `site-content/`, без запуска workflow/build.py форка.
Точная схема manifest/ссылок/проверок — [ROOT-IMPORT-V1.md](ROOT-IMPORT-V1.md).

`points.json` оставить совместимым для статического demo. Versioned manifest
фиксирует schema/root revision, исходный commit, content digest, namespace,
даты и root edges. Даты не из mtime: creation фиксирована, update зависит от
content/links digest, build_time отдельный. Unknown historical date помечать.

### Таблицы и ограничения

| Таблица | Инварианты |
|---|---|
| `users`, `sessions` | Одна учётка сервиса, active state, password hash, expiry/revoke; глобальный session не передаётся чужому parent |
| `sites` | PK=s_point ID; unique verified origin; owner; welcome source; state; immutable public ID; план ресурса |
| `site_members` | Explicit owner/editor roles; не привилегии над shared neighbours |
| `site_claims` | Challenge digest, normalized origin, expiry/attempt count, verified time; no implicit claim by embed |
| `points`, `point_revisions` | PK стабильный ID; origin=root/user/site; immutable body/declared refs/citation pins/editor/source revisions, current pointer, author, lifecycle |
| `root_sources`, `root_revisions` | site/core namespace, registered repo+ref+subtree; immutable SHA/digest, candidate/active run |
| `point_edges` | PK(a,b), CHECK a<b, FK; одна semantic relation; provenance claims отдельно |
| `edge_claims` | edge + source revision/creation op; removal одного import не снимает чужой claim |
| `point_reactions`, `reaction_history` | PK(user,point), value±1, endorsed_revision, confirmed/pending; один голос независимо от site/iframe |
| `notifications` | Личный inbox, durable fanout/cutoff/dedup, old/new revisions, read state; parent не читает личные данные |
| `user_supports` | PK(source,target), no explicit self; один global trust graph |
| `events` | committed order, schema/operation ID, before/after, timestamps, provenance incl site when applicable |
| `embed_grants` | user+site+verified parent origin+capability+expiry/revocation; не доверять site_id URL как grant |
| `idempotency_keys` | actor+operation+key/request digest; повтор transport/iframe не создаёт новый point |
| `calculation_runs`, derived tables | input cutoff/config/version/digest, last-good pointer, reproducible caches |
| `site_plans`, `usage_counters` | server-owned entitlements и атомарные счетчики; embedding ID не доказывает оплаченный доступ |
| `moderation_actions` | operator, target, reason, audit; sanitized public projection |

Индексы по обоим концам edges; reactions/trust source и target; feed sequence,
point+sequence, author+time; origin registry; source/revision; session digests.
Migrations/гонки на настоящем PostgreSQL, не на SQLite substitute. Рассчитать
стоимость `edge_claims`: импорт/сайт/авторское создание имеют различимое
происхождение, чтобы один source не удалял связь другого.
Индексы поиска текущего текста обновляются транзакционно с revision pointer;
исторические версии доступны по явному ID и не смешиваются с обычной выдачей.

### Атомарность, импорт и журнал

Root import: schema/files/IDs/URLs/edges/limits → preview diff → accepted run →
atomic source pointer. Нельзя частично опубликовать 8 из 10 файлов. Повтор commit
— no-op. Временно пропавший GitHub не retire-ит roots; сохраняется last-good.
Удаление файла даёт pending retire в preview, не cascade реакций/истории.
Root source меняется только его owner; Git welcome и UI welcome взаимоисключены.

Social mutation, edge, reaction, time and event фиксируются вместе. PUT same
value / DELETE absent — no-op без повышения активности. Reactions idempotent;
POST point обязательно request key. Смена support→oppose — один operation ID,
с полным before/after; связанная новая точка обновляет last_interaction соседей.
Правка обновляет активность авторской точки; изменение её ссылок — затронутых
концов один раз за operation. Чтение, reload iframe, visitor counter,
прочтение уведомления и import unchanged этого не делают. Возможное оформление
старой точки трещинами выводится из last_interaction, без abandoned-флага и без
автоматического уменьшения массы. Edit spam ограничивается квотой.

Event seq не является автоматически commit order. MVP использует короткий
transaction advisory lock вокруг social mutation/event sequence; freeze cutoff
согласован с тем же порядком. Network/root fetching/hash выполняются вне lock.
Тест задержанного commit обязателен. История includes site verify/deactivate,
source import/retire, revisions, point create, trust/reaction и moderation.
Пароли/session secrets там отсутствуют. Body redaction может ограничить
исторический текстовый replay и описывается политикой, не скрывается.

## 7. HTTP, UGC и сессии

Точный актуализированный draft — [API-V1.md](API-V1.md). Единый `/api/v1` для
shared graph; site ID задаёт контекст входа/темы/квоты, а не tenant partition.

| Группа | Поставка |
|---|---|
| Health/meta | live/ready, versions, capabilities, root revisions, latest snapshot, configured limits |
| Auth | register/login/logout/me, отдельный trusted top-level login, recovery и scoped embed grants |
| Sites | claim/verify/read/settings, welcome revision, theme, origin aliases, disable/reverify |
| Point/field | lookup shared ID, bounded depth1/2, neighbours cursor, origins/provenance |
| Create/edit/reactions/trust | author/source ACL, immutable revisions, atomic writes, idempotency, one vote across all sites |
| Notifications | Личный общий inbox, diff изменённых поддержанных точек, подтверждение новой версии |
| Feeds/search | global и mine; optional site entry view не изолирует граф; search targets bounded |
| Root imports | owner preview/accept/status, fixed registered GitHub source, immutable revision |
| Usage | own limits/current consumption/retry, server-authoritative counters |

Point creation proposal: 1–16 distinct existing targets, body1–8192 Unicode
symbols/32KiB UTF8. Returned error envelope code/message/request_id, explicit
413/422/429 Retry-After, 401/403, conflict409, stale import/version and ready503.
Root fields выигрывает их active source revision; dynamic API не переписывает
canonical root body. Safe snapshots доступны через same-origin bridge/hosted
API — другие сайты не обязаны скачивать весь Git root index сервиса.

Field proposal cap200 nodes/600 edges; ограничить SQL expansion, не только JSON.
`degree_total` и `degree_visible` разные. Общий directory hub `all-sites` имеет
cursor page вместо взрыва depth2 (§5); `truncated` всегда явен. Feed limit30/max100,
keyset upper cutoff/filter revision, mine OR-dedupe. Cursors без session secrets.

Auth baseline: opaque random256bit secret, digest в БД; Argon2id для password,
измеренная стоимость; plaintext/hash/password никогда в API/logs. Идентичность
одна на сервис. Однако automatic silent SSO на любом embedded сайте не обещать:
scoped grants и ограничения third-party storage определены в EMBED-V1.

**Недоверенный parent — принципиально новый риск сервиса:** origin verification
доказывает владение сайтом, а не честность его JS. Поэтому bridge не передаёт
ему глобальный bearer, password или admin API. Привилегии управления сайтом,
Git sources, кошельком и recovery доступны только trusted management UI.

CORS exact origins нужен opt-in direct clients; bridge/full embed ходят в
same-origin API. Allowlist postMessage != CORS != auth. Все три проверки
раздельны. `credentials: omit` в embed API с ограниченным bearer; management
first-party cookie/session и CSRF обрабатываются отдельным контуром.

UGC: textContent или проверенный Markdown parser/sanitizer, raw HTML off.
Никаких arbitrary scripts/iframes, `javascript:`, `data:` URLs, on* handlers;
external URL только обычные ссылки. Никакого unfurl/server fetch по тексту.
Git roots также недоверенный Markdown: владелец форка не оператор сервиса.
Root imports и origin verification — два narrowly-scoped network executors,
не универсальный fetch endpoint. Сохраняются fixtures parser placeholders,
quotes/entities, links, dynamic IDs, long input и unknown targets.

### Авторство, изменение смысла и поиск при письме

Права MVP: автор правит свою DB-точку и её объявленные ссылки; владелец сайта —
своё приветствие; Git roots меняются через источник. Владение сайтом не даёт
прав на все тексты посетителей, близость в графе пока вообще не выдаёт прав.
Снятие своего edge claim сохраняет встречные/чужие claims. `expected_revision`
и транзакционная проверка защищают параллельные изменения от потери текста.

**Требование:** поддержавший должен узнать, что поддерживаемая точка изменилась.
**Предложение защиты:** неизменяемые версии тела/авторских ссылок, поддержка
конкретной прочитанной версии. После любой такой правки поддержка становится
pending; новая формулировка не получает старую массу автоматически. Inbox
показывает безопасный diff и позволяет подтвердить новую версию, возразить или
снять реакцию. Изменения Git импортом подчиняются тому же правилу. Тема, входящие
ссылки, чтение и no-op ничего не переподтверждают. Накопленные уведомления
группируются, но история сохраняется; даже возврат старого текста требует
явного подтверждения. Детали outbox/fanout и гонок — API-V1 §4.

Редактор: выделить «воля» → поиск по всем точкам → увидеть определение, автора,
сайт/источник и версию → выбрать → вставить ссылку либо оставить слово текстом.
Поддерживаются фразы, клавиатура, снятие ссылки без удаления слова, одинаковые
слова с разными значениями. Подсказки не требуют заголовка у точки, не создают
новые точки автоматически и не превращают все совпадения в ссылки.

Пример владельца: «[воля](md://point/r_example_will) влияет на длительность
воздействия» в авторской публикации ссылается на выбранное лорное объяснение.
Это фиксирует, что автор использует именно этот смысл. Утверждение об эффекте
принадлежит публикации; автор определения не становится его соавтором или
подписантом. Если нужно отдельно обсуждать причинную связь, предлагается
выделить её в самостоятельную точку-утверждение со ссылками на оба понятия;
типизированная онтология и обязательные теги для этого не нужны.

Ссылка хранит ID смысла и выбранную версию объяснения. При чтении можно открыть
цитируемую версию и увидеть обновление. Если цель изменилась между поиском и
публикацией, 409 предлагает сравнить/перевыбрать либо явно цитировать старую
доступную версию. Простое ребро остаётся между постоянными ID. **Открыто D17:**
выбор ссылки и голос поддержки предлагается разделять, с отдельным явным
действием «Также поддержать». До ответа владельца автоматический расход
влияния не вводить. Пример не утверждает новую формулу игровых навыков.

Географическая модерация — отдельное позднее исследование: определить расстояние
(число рёбер/социальные координаты), право и устойчивость к манипуляциям. Близость
может предлагать кандидатов на модерирование, но перемещение точки не должно
само давать права изменять канон/чужой текст. В MVP только авторство, явные роли
сайта и журналируемые действия оператора. Порог и делегирование не придуманы.

## 8. Доверие и масса: сначала проверяемый расчёт

API фиксирует 1 unit base influence на active user **во всём общем графе** и бюджеты people=0.5,
points=0.5. Владелец утвердил T1 для первой версии с проверкой сохранения
влияния. Реализованный численный контракт: [SOCIAL-V1](SOCIAL-V1.md).

Регистрация сайта, импорт Markdown, второе iframe и открытие того же пользователя
на другом сайте не добавляют base mass. Site points и Git roots — terminal sinks,
как обычные points. Каталог не передаёт массу всем сайтам.

Пусть N — число активных пользователей, `T[i,j]=1/(k_i+1)` для self и каждого
активного поддержанного человека. Иначе T=0. T row-stochastic.

```text
w(0) = [1, ..., 1]
w(t+1) = (1-d) * [1, ..., 1] + d * transpose(T) * w(t)
0 <= d < 1; утверждённый v1 d = 0.5
people_i = 0.5 * w_i
point_budget_i = 0.5 * w_i
n_i = число confirmed И pending положительных реакций i
contribution(i,p) = point_budget_i / n_i, если confirmed support(i,p)
held_pending = sum_i (point_budget_i / n_i) * pending_positive_count_i, n_i > 0
mass_p = sum_i contribution(i,p)
idle = sum_i point_budget_i, для пользователей с n_i = 0
```

`w` — нормированное распределение эффективного влияния, не ещё один запас
поверх people/points. Матрица T и damping вычисляют его, не выдают новую валюту.
Отрицательная реакция не переводит положительную массу. Авторство и ребро сами
массу не создают; точки — конечные приёмники, никогда не передают её автору.

Проверяемые равенства:

```text
sum(w) = N
sum(people) = N/2
sum(mass) + held_pending + idle = N/2
sum(people) + sum(mass) + held_pending + idle = N
```

Примеры при d=0.5: один человек без поддержок имеет w=1 и idle=0.5; поддержка
двух точек даёт по 0.25. Два взаимно поддерживающих человека имеют w=(1,1).
Если A поддерживает B, а B только себя, решение w=(2/3,4/3), не (1,2).
Добавление публикаций без новых пользователей не меняет N.
Если из двух поддержанных точек одну изменили, её 0.25 уходит в held_pending,
другая остаётся 0.25. Подтверждение возвращает долю новой версии, снятие реакции
явно меняет распределение. Это утверждённое поведение T1 v1.

Суммарная погрешность proposal ≤1e-9*max(1,N), L1 residual проверяется; максимум
итераций 128, non-convergence/NaN/negative result не публикуются. Обход ID
детерминирован; алгоритм/config/version/input digest сохраняются. Не округлять
до двух знаков на промежуточных этапах. Rounding — только UI.

Проверить N=0, isolated users, кольца, звезду, clique, asymmetric graph,
block/reactivate, remove trust, remove final point support, одинаковый input
в ином SQL order. Sybil-атака всё ещё добавляет N через новые аккаунты: сохранение
массы не доказывает независимость людей. Защита регистрации нужна отдельно.

### Публикация вычислений

Текущий worker примерно раз в 30 секунд под общей транзакционной блокировкой
графа фиксирует cutoff, считает trust→mass→geometry и проверяет сохранение бюджета.
Он добавляет неизменяемую запись influence_runs с input digest; чтение выбирает
последний опубликованный run, а не несуществующее поле published_run_id.
Ошибка сохраняет последнюю удачную раскладку с явным pending/unavailable.
Дополнительные worker не записывают конкурирующие графовые транзакции.
Порог degraded-after пока не является установленным SLA.

Читатель сравнивает cutoff, активные аккаунты и pin текста. Чужая версия не
получает старые координаты. Последние удачные координаты того же текста могут
оставаться видимыми с pending до пересчёта; свежая масса при этом не выдумывается.
Пакеты карты используют один snapshot ID, не смешивают разные runs и явно
сообщают об отсутствующих точках вместо тихой частичной замены раскладки.

## 9. Шесть координат и настоящий социальный движок

**Решено:** 6 чисел, не RGB; projection в 3 пары только в интерфейсе; цвет,
масса и confidence — независимые каналы. Complementary pairs:
cyan/red, magenta/green, yellow/blue. У текущего `relativeAxis` знак компоненты
и направление цветного луча требуют фиксированной таблицы и golden cases:
не переставлять индексы неявно.

**D05 выбран владельцем 23 октября 2026:** вариант с перестановкой
противоположных пар. Пользователь задаёт шесть положительных координат (цвет),
подписка вносит нормированный вектор, явная блокировка — `[B,A,D,C,F,E]`.
Обычная отписка нейтральна. Оба типа реакции делят один бюджет T1; общего
влияния не прибавляется. Итоговые координаты — взвешенная сумма подтверждённых
вкладов, проекция остаётся относительной. Это заменяет прежние кандидаты
self-anchors/PCA и промежуточный вариант вычитания компонентов.

Точный численный контракт, диапазоны, привязки к версиям, Git-перенос, API,
начальная раскладка, границы и rollback: [SOCIAL-GEOMETRY-V1](SOCIAL-GEOMETRY-V1.md).
Confidence и радиус по социальной массе пока не внедряются; размер сферы
по-прежнему означает степень связности. Нулевая выборка не создаёт координаты.

Golden datasets: пустой мир; один сторонник; четыре согласованных; два
противостоящих кластера; межкластерная точка; новая isolated point; симметрия
полюсов; roundtrip проекции; zero pair; identical coordinates; резкое удаление
аккаунта; permutation invariance. Публичный экспериментальный отчёт показывает
до/после и выбранные коэффициенты до замены synthetic geometry.

F–S hierarchy и recursive containment/color layers — P10, после ядра.
Несколько изолированных миров не являются текущей архитектурой: открытый лор
владелец поместил в shared graph. Кастомный домен не создаёт другой мир. В каждом случае отдельная ADR: чего добавляет механизм, как не
меняет raw edges/authorship, какие данные экспортируются. Не записывать
вычисленного родителя обратно в point_edges. Пользовательская публичная точка
должна ссылаться на отдельный user ID, не включать password/session поля и не
давать автоматической массы по двум путям.

## 10. Три фронтенда из одного исходника и оформление

### Локальный UI + bridge

Neocities хранит свою HTML/CSS/JS оболочку, roots demo и versioned SDK.
Point-store читает public dynamic data через hidden bridge; root static fallback
сохраняется. Локальный CSS может оформлять весь этот DOM. Обновление SDK можно
делать через Git fork/release, без runtime исполнения ответов GitHub/API.

### Full iframe и hosted-вики

Одинаковый renderer/point-store/router используется как hosted standalone и
`/embed/v1/sites/<s_id>/`. Full iframe показывает целую вики, не только welcome:
поле, тексты, реакции, лента и навигация по **всему** shared graph доступны по
правам. Без явного point ID начинает с site point. При переходе на другой сайт
в графе welcome/point меняется, shell theme остаётся того embedding сайта,
пока человек не выбрал внешний переход. Browser back/deep links сохраняют ID.

Hosted-вики полноценно работает вне iframe; абсолютный service permalink можно
передать другу. Embed page имеет обычную «Открыть отдельно» ссылку. Новые site
records/root imports не требуют deployment кода; renderer получает runtime
config и bounded snapshots. Git mirror хранит только public static outputs,
не live DB и не аккаунты.

### CSS и пользовательское оформление

CSS родителя не наследуется внешним iframe. **Решение предлагаемого MVP:**
локальный `.css` задаёт публичные `--node06-*` переменные на iframe/container;
loader читает допустимые значения и посылает theme message. Full iframe
проверяет поля и применяет только известные tokens. Сохранённая owner theme
работает и с bare iframe без loader. Пример и exact allowlist — EMBED-V1.

Произвольный URL stylesheet не принимается: такой CSS может скрывать действия,
подменять интерфейс или обращаться к внешним адресам. Элементы входа/согласия и
служебные сообщения не подчиняются tenant theme. Свободная стилизация доступна
через local UI + bridge; расширенный CSS для full embed — будущая отдельная
изолированная реализация, а не необходимая фича запуска.

### Навигация, язык, доступность

- Header/H1 NODE06 на demo ведёт на `/`; там общая стартовая. После появления
  social service стартовое содержимое demo берётся из его `s_id`, с сохранением
  существующих языковых ссылок и deep links.
- В embed «Главная этого сайта» возвращает к `s_id`. «Все сайты» ведёт к
  `all-sites`. Эти две команды не зависят от языка UI.
- Единственный адрес поля — `/?p=<id>&open=<id>`. `/en/`, `/ru/` остаются
  только redirect для старых ссылок с сохранением явного `p`; без него — `/`.
  Нет языковых shell, локализации приложения по языку точки, translation_group
  и фильтра графа/ленты по языку. Любая точка может содержать любой язык;
  начальные RU/EN точки — самостоятельные объекты с обычными связями.
- Welcome редактируется отдельно каждым owner, source UI/Git объявлен явно;
  можно добавить ссылки на свои root MD, кнопку сайта и короткое вступление.
- При недоступности API: static roots demo readable; full iframe fallback —
  пояснение/retry/standalone link. Не выдавать missing dynamic point за root.
- AbortController/request generation: устаревший ответ не меняет новый центр.
- READ/EXPLORE/FEED и три docking варианта сохраняются; клавиатура, touch,
  текстовый список соседей, focus, 320px viewport и reduced-motion обязательны.
- Root/user/site происхождение видно в карточке. Цвет не заменяет подпись
  canonical/source/import; покупка тарифа не раскрашивает достоверность.

### Баннеры 88×31

88×31 — подходящий исторический формат обменных кнопок
([IndieWeb 88x31](https://indieweb.org/88x31)). Это ручные ссылки на соседей,
а не рекламная сеть. Выделить тихую полосу/страницу «соседи» на `/` и About,
не забивать постоянно движущимися картинками рабочее поле.

**Свой баннер, рекомендуемый эскиз «тихий узел»:**

- 88×31 PNG, читаемый bitmap NODE06; тёмно-фиолетовая/почти чёрная основа;
- маленькая серебристая сфера, шесть цветных контактов, один обрывающийся провод;
- короткая подпись `A SMALL WORLD` либо `ENTER THE FIELD`, один вариант выбрать;
- свечение каждого контакта совпадает с его цветом; форма читается без цвета;
- основная версия статическая, необязательная медленная GIF-вариация после
  проверки reduced-motion; без строба, автозвука и ложных системных предупреждений;
- знак намекает на самостоятельный узел/наблюдение, не объясняет скрытую космологию;
- production PNG проверяется в реальном размере, не только на крупном макете.

Дополнительный концепт «соединённые мыслью»: NODE06 и две сферы, между ними
возникает третья. Он точнее показывает действие пользователя, но хуже читается
в 88×31; оставить запасным художественным направлением.

Техническая поставка P09: `static/badges/node06-88x31.png`, при необходимости
2x176×62 export для Retina, editable source в выбранном art workflow, credits,
постоянный URL и простая копируемая HTML-вставка с alt/width/height. License
собственной кнопки утверждается и явно заносится в LICENSES, а не наследуется
случайно как всё `static/**`. Не ставить весь чужой art под AGPL.

Набор первых внешних кнопок: IndieWeb, Neocities, Hexrelatum, Geno-Dice, личный
сайт автора/друзья по выбору. Использовать только предоставленный владельцами
asset с понятными условиями, без выдуманной принадлежности к webring/сертификации.
Источник, автор, license/permission, URL назначения, размер, дата проверки —
в `docs/asset-credits.md`. Коллекция картинок не доказывает разрешение.
Если готовой кнопки нет — обычная текстовая ссылка до появления согласованного
asset. Не hotlink чужие картинки без необходимости; visitor не должен
обращаться к нескольким трекерам, чтобы увидеть нижнюю полосу.

Улучшения P09+: читаемые статические root permalinks, RSS/Atom новых точек,
export своего публичного вклада, страница link-to-us и colophon, ручные
webring/blogroll ссылки. Webmention/IndieAuth — позже, с отдельной моделью
проверки источников и спама. Наличие кнопки IndieWeb само по себе не означает
реализацию этих протоколов.

## 11. Лор и социальный эксперимент

Ценность сервиса: посетители разных сайтов действительно меняют общее поле своим вкладом,
а не только читает рекламный тизер Geno-Dice. Корневые «наблюдение», «внешнее»,
«поле» и `welcome` уже дают подходящее чувство обнаружения.

**Предложение трёх уровней подачи:**

1. Самостоятельный инди-веб: понятное поле мыслей, человеческие тексты и ссылки,
   честные правила участия. Работает без знания Geno-Dice.
2. Находки для любопытного: редкие фрагменты/переклички и следы прошлых эпох;
   открываются обычной навигацией, не требуют массового голосования.
3. Открытый лор через будущий `wiki.geno-dice.com`: своя site point и Git roots
   в том же shared graph, только отдельно отобранные публичные тексты;
   полное объяснение остаётся в общей документации и закрытом авторском слое.

Не создавать сейчас «секретные» public JSON-флаги с расшифровками. Всё в public
Git, dist, source maps, API, alt, SVG metadata и asset filenames доступно
исследователю. Тайна — повествовательное дозирование, не фронтенд access control.
Закрытый контент не должен попадать в сборку вообще.

Каждый новый фрагмент проходит checklist: источник/статус канона; самостоятельный
публичный смысл; разрешённая глубина раскрытия; RU/EN как отдельные authored
точки; license/author; связи взаимны; узнаваемость без объяснения; отсутствие
private data в артефакте. Внутренние заметки связывают его с лором, не public ID.

Социальные правила публикуются обычным языком: какие действия изменяют веса,
что видят другие, период пересчёта, почему бывают неопределённые координаты,
как работают модерация и экспорт. Нельзя изображать фальшивых пользователей,
генерировать тайные голоса для нужного сюжета или выдавать художественный glitch
за реальную утечку/взлом. Seed/боты, если появятся, явно отмечаются.
Популярность не становится авторским правом, модерацией или правом изменить канон.

## 12. Злоупотребления и эксплуатационная готовность

Это практические задачи публичного user-generated сервиса, не повод превращать
MVP в корпоративную платформу:

- Закрытая synthetic/dev стадия, затем ограниченная alpha, затем открытая
  регистрация с прозрачными квотами. Invitation beta — предложение, не смена
  целевого открытого участия. No email/SMS/CAPTCHA по умолчанию без необходимости.
- Rate limits на IP и account: proposal register 3/hour/IP, login 10/min/IP
  плюс account backoff, create 10/hour/user, reactions/trust 60/min/user;
  проверять общий NAT и возможность abuse. Лимиты — config, не константа лора.
- Nginx ограничивает IP, приложение — account/shared Postgres counters.
  In-memory limiter нескольких workers нельзя выдавать за глобальный.
  Forwarded IP принимать только от своего reverse proxy.
- Request size, link counts, pagination, statement/request timeouts и query
  limits защищают от graph explosion и password-hashing exhaustion.
- До публичной записи нужен минимальный operator CLI: hide/restore point,
  block/reactivate user, revoke sessions, inspect sanitized moderation history.
  Жалоба — понятный контакт/форма по принятому решению; moderation не reaction.
- Hidden point не возвращает текст через field/feed/search/profile/export.
  User-facing tombstone не раскрывает private reason. Blocked users и их
  голоса исключаются по versioned active-set policy; история сохраняется.
- Удаление аккаунта/контента, recovery, export, сроки хранения событий/logs и
  backups сформулировать до open launch; отказ обещать абсолютную анонимность.
  Политика удаления может ограничить replay текста — это описать прямо.
- Публичные документы об участии, видимости и обработке данных согласовать
  до запуска; этот план не является юридическим заключением и не делает выводов
  об обязательствах только из расположения сервера в Амстердаме.
- Logs: request ID, status, duration, counters; без Authorization/password/body,
  query-токенов и дампов. IP retention минимальна и объявлена.

### Квоты и будущая монетизация

Первый шаг монетизации — простая явная ссылка «Поддержать сервис» на согласованную
страницу существующего кошелька. Не внедрять оплату внутри iframe, не выдавать
после return URL тариф или GC. В этом этапе нет SDK acquiring, webhook, invoice,
платёжных секретов, новой валюты или импорта финансовой базы на Амстердам.

С самого MVP заложить quotas/usage/feature flags, но не выдумывать цены:
`site_plans` и server-owned entitlements. Первый free plan и operator trial
используют одну схему будущих tiers. Donation сама по себе не меняет лимиты.
Если появятся платные планы — wallet-owned подтверждение оплаченного права,
идемпотентная доставка entitlement и отдельное согласование продукта.

Метрики лимитов: site roots count/bytes, import frequency/candidate size,
verified aliases, cumulative source storage, authenticated write rate,
concurrent jobs и costly reads. Вдобавок global/user/IP quotas. Один public
`site_id` легко скопировать: не выставлять счёт только по входному query/site ID.
Signed/scoped embed grants дают attribution, а анонимное чтение всё равно
защищается общими budget/cache/abuse ограничениями. Host header и Referer не
доказательство покупателя; обход лимитов через standalone/import API запрещён.

Предложение начальных мягких пределов на site: 100 root MD, 1 MiB суммарного
root text, один import одновременно, не чаще одного приёма раз в 15 минут.
Точные размеры проверить по нагрузке; это research defaults, не объявленный
тариф. Социальные ограничения user/shared остаются отдельными: через многие
сайты нельзя создавать N аккаунтов/голосов за одного участника автоматически.

Показывать usage/remaining/reset и причину 429; заранее предупреждать о лимите.
Не удалять общие точки после понижения тарифа; сначала остановить новые imports
или дорогостоящие операции, сохранить чтение/export и last-good state. Paid
capacity не даёт массу, ранжирование, канон, дополнительные голоса или moderation.
Server circuit breaker может временно заморозить costly imports/geometry,
сохраняя bounded read и last-good snapshot. Donor badge, если появится, отдельный
визуальный канал от influence/confidence.

## 13. Амстердам: hosted frontend, embed и API

Live сервер **не исследовался** этой задачей. До deployment нужны inventory,
точные домены/порты/пользователи/ресурсы/DB, совместимость текущего recovery и
соседних сервисов. Backend/frontend остаются независимы от Wagtail и кошелька.

Proposed routes, не действующие URL:

```text
<service-origin>/                  hosted wiki + user-facing service entry
<service-origin>/sites/<s_id>/     standalone entry конкретного сайта
<service-origin>/api/v1/           same-origin API для hosted
<embed-origin>/bridge/v1/<s_id>/   маленький transport document
<embed-origin>/embed/v1/<s_id>/    полный UI
<embed-origin>/api/v1/             scoped API proxy к тому же backend
<auth-origin>/                    top-level login/management, frame-ancestors none
wiki.geno-dice.com                 будущий официальный frontend, fixed lore s_id
```

Точное разделение DNS можно сократить на старте, если auth/management всё равно
не встраиваются и не принимают theme/custom content. Предпочтение — изоляция
management от embed origin. Это не три базы: same backend DB, same public graph,
одни provenance и события. Full assets доставляются одним версионированным
artifact в hosted/embed outputs; frontend fixes не расходятся между копиями.

Nginx TLS: same-origin API proxy, security headers **по маршрутам**.
Для embed/bridge frame-ancestors из зарегистрированных точных origins по site;
для generic read-only embed отдельный явно public режим; для login/manage
frame-ancestors none. Не ставить глобальный X-Frame-Options DENY/SAMEORIGIN на
embed. CSP cache key включает site/origin policy revision, иначе можно выдать
заголовки другого tenant. Credentials-bearing ответы не shared-cache.

Привилегированные scripts/Nginx/backups принадлежат `geno-dice-deploy`. NODE06
пока отсутствует в deployment allowlist. Добавить целевой project только после
review, не включать автоматически общий timer всех сервисов.

Порядок первого rollout, будущая отдельно авторизованная задача:

1. Inventory/trusted host; выбрать origin topology, DB/runtime/deploy roles,
   limits. Проверить DNS/TLS, не переносить wallet на Амстердам.
2. Exact reviewed SHA + lock + CI; create/test-restore DB backup, validate env
   без вывода значений. Отдельный runtime user, loopback API, DB least privilege.
3. Alembic под single deployment lock; import core roots/all-sites, demo pending
   site, prove origin, activate; первый shared snapshot. Без fake user mass.
4. Раздать versioned hosted/bridge/embed assets, установить route-specific CSP,
   проверить auth denial-of-framing, origin revoke и cache isolation.
5. Два контролируемых внешних сайта (включая Neocities Free) проходят full и
   bridge E2E, локальный CSS tokens, вход с cookies off, shared votes и deep links.
6. Третий fixture fork проходит import preview/accept и correction/retire;
   ломаный/враждебный import оставляет last-good. Не запускать GitHub code.
7. Проверить quotas, owner separation, downtime/restore/rollback, bounded
   all-sites hub, failover «Открыть отдельно», alerts и operator moderation.
8. Alpha ограниченного числа владельцев; затем open onboarding по измерениям.
   Будущий официальный lore frontend добавляется как site, не новая база.

### CI, совместимость и восстановление

- Static source один; Neocities bundle и hosted/embed artifacts versioned.
  Только allowlisted public roots/JS/CSS/assets в outputs. Не shipping DB/env.
- CI: static checks; backend PostgreSQL/migrations; malicious imports;
  protocol/auth/CSP/theme E2E на разных origins; contract golden fixtures.
  PR не получает production credentials. CI форка — у владельца форка, без
  доступа к нашим runners, tokens и deploy keys.
- SDK/protocol major pin; сервер поддерживает текущую и предыдущую совместимую
  версию. Old loader получает readable upgrade notice, не непонятную поломку.
- Runtime site/theme/root updates без deploy статической демо-сборки. GitHub
  polling отдельно bounded job, secrets отсутствуют для public repo read.
- Rollback: запрет writes/import intake → last-good frontend/protocol + API SHA
  + root/source pointers + snapshot; shared data не теряется от возврата assets.
  Миграции additive; несовместимый schema rollback только с reviewed restore и
  учётом новых writes, не автоматический downgrade.
- Backup proposal daily encrypted off-host dump, 7daily/4weekly, manifests и
  source revisions/config schema. RPO24h/RTO4h — цели, доказать restore drill.
- Метрики: errors/p95, DB pool, shared snapshot lag, import backlog/bytes, costs
  по безопасному attribution, quota reject, disk/backup age. Logs без tokens,
  private text и полного содержимого пользовательских страниц.

## 14. Пакеты работы и приёмка

Это новая последовательность редакции 2: старые ссылки на P-номера сверять с
этой таблицей. Каждый пакет завершается малым PR, evidence и обновлением Progress.

| ID | Зависит | Задача | Критерий завершения |
|---|---|---|---|
| P00 | — | Прототип bridge/full embed/тема/auth handoff под точным CSP Free | Два разных origins; CSP parent блокирует fetch, bridge roundtrip работает; blocked storage, timeout/reload, spoof message rejected; real-origin proof отдельно |
| P01 | P00 contracts | Backend/config/PG/migrations/CI, hosted/embed build targets | Fresh PG upgrade; independent static build; exact artifact/version/config |
| P02 | P01 | Site claim/verify/welcome/all-sites/settings | Два verified сайта дают две `s_` точки в одном графе; duplicate/reclaim/unauthorized changes rejected |
| P03 | P01,P02 | Auth/recovery/scoped embed sessions | Нет глобальных credentials у parent; no third-party cookie dependency; revoked origin/grant fails; consent grants exact action |
| P04 | P01,P02 | Core + site Git import, stable ID/provenance/edge claims | Manifest validation, preview/accept, namespace collisions, fork/core dedup, missing target/SSRF/symlink/cross-source deletion rejected |
| P05 | P02–P04,D16,D17 | Public point/field/search, create/edit/revisions/reactions/trust/events/inbox | Atomic idempotency, commit-order, bounded hub, one user vote across sites, same point in hosted/full/bridge; author ACL, edit/reaction races, durable notifications |
| P06 | P05,D03,D16 | Pure trust/mass + shared snapshots | Conservation N incl held_pending, stale-revision gate, no site/fork mass, deterministic rebuild and last-good publish |
| P07 | P06,D05 | Opposite-pair geometry v1 | Six values, normalized profiles, support/block budget conservation, version pins and shared anonymous projection; confidence deferred |
| P08 | P03–P07 | Общий renderer/SDK/standalone/full/local UI, semantic editor/diff/inbox | Default `s_`, full navigation, deep links/history, local CSS tokens, version-pinned word links, plain words, homonyms, old SDK compatibility, keyboard/mobile |
| P09 | P02,P08 | Onboarding UI, docs/snippets, demo, badges/link-to-us | Nontechnical owner connects Free site; CSS preview; copy snippet has no secret; correct support/source links |
| P10 | P06–P08 | User-concept/F–S research | ADR + fixtures; derived hierarchy не меняет raw source/authorship; optional feature off |
| P11 | P02–P09 | Moderation/export/quotas/usage; wallet link later | Owner isolation; no arbitrary CSS/script; downgrades retain data; wallet plain link only |
| P12 | P11 + explicit deploy authority | Amsterdam real alpha + Free E2E + load/restore | 2 independent sites+fork, hosted+both embeds; no secret leak; measured host budget; operator rollback |
| P13 | P04,P08,P11 | Открытый lore frontend на будущем wiki.geno-dice.com | Lore site point и approved roots в shared graph; general links work; only authorized editors change canonical sources |
| P14 | Measured demand | Resource tariffs/entitlements | Pricing separately approved, server-enforced quotas, wallet verified billing contract if needed; payment never buys influence |

P00 исследует механизм и не открывает production; P12 доказывает реальную
доступность на Free. Не ждать геометрию для read-only embed alpha, но не объявлять
alpha завершённым concept engine. P09 badges можно делать раньше независимо.

### Матрица обязательных проверок

| Группа | Проверки |
|---|---|
| Existing static | 23 initial roots/35 edges и orphan сохраняются до intentional content additions; header/H1→`/`; RU/EN cross-links |
| Site registry | Verify replay/race, wrong file/origin, reused domain, alias proof, owner/coowner scope, delete/tombstone |
| Shared graph | A/B/hosted видят один ID/одну реакцию; general↔lore navigation; site count не входит в N |
| Bridge | origin/source/session/nonce/version/size checks, request timeouts/reload, no arbitrary URL/method, 429/backpressure |
| Auth | blocked cookies/popup, spoof auth result, PKCE/code replay, logout across grants, parent cannot get global token or admin action |
| Theme | parent CSS doesn't auto-cross; allowlisted local tokens do; malicious CSS values/url ignored; auth unthemeable |
| Import | public pinned SHA, repo proof, GitHub unavailable, changed branch, partial files, traversal/symlink/LFS/html, root IDs protected |
| Root edges | intra-source reciprocity, explicit external refs, edge claims independent, import retry/retire leaves user data |
| API/PG | FK/unique/race, idempotency, strict validation, bound search/field hub/feed, CORS and route-specific frame CSP |
| Edits/search | author vs site ownership; semantic homonyms/phrases/plain text; citation revisions; diff inbox; source edits; pending/reaffirm races |
| Math | pending holds/stale revision gate/cycles/stars/idle, N conservation globally, unchanged on second site, mass not degree, reproducible cutoff/rebuild |
| Lifecycle | owner transfer/revoke, code version old SDK, source revisions rollback, database restore, shutdown/degraded fallback |
| Quotas | simultaneous writes/imports atomic, cheap ID spoof no entitlement, global+site+user limits, downgrade no deletion |
| Accessibility | keyboard/focus, iframe title, 320px, mobile scroll/resize, reduced motion, external-open fallback |
| Lore/finance | no hidden source in public artifacts; source ACL despite same graph; wallet return URL never grants paid plan |

Нагрузочная модель proposal: 100 sites/1k users/10k points/100k edges+reactions,
плюс hub10000 sites stress, 20 concurrent readers и overlapping import jobs.
Измерить p95 bound field/feed (<500ms исходная цель), snapshot<30s при cadence60s,
import queue fairness/memory и диск. Это цели исследования, не результаты.

## 15. Реестр решений

| ID | Решение | Статус/остаток |
|---|---|---|
| D01 | Bridge + full iframe, Neocities Free | Выбрано владельцем; production feasibility проверяется P00/P12, не покупать Supporter |
| D02 | Один repo/API/DB и hosted frontend Amsterdam | Выбрано направление; versions/domain topology подтвердить P01/P12 |
| D03 | Смысл support/oppose и T1 formula | T1 v1 принят: damping 0.5, точные полубюджеты; SOCIAL-V1 |
| D04 | Автор редактирует свои точки и ссылки | Новое требование отменяет общий create-only запрет; чужие пары/источники недоступны |
| D05 | Social coordinates | Выбран opposite-pairs v1; нормировка координат, общий T1-бюджет; SOCIAL-GEOMETRY-V1 |
| D06 | Users as mapped points | Отдельная безопасная projection, no double mass; details deferred |
| D07 | F–S | Исследование после reliable graph, не обязательная скрытая миграция MVP |
| D08 | Recovery/retention/moderation | Определить публичные правила до open signup |
| D09 | Host/DNS/cost budget | Amsterdam выбран; endpoints пока placeholders, live inventory требуется |
| D10 | Баннер/публичные lore fragments | Выбор конкретных assets/text до публикации; no full hidden explanation |
| D11 | Site points/welcome/shared graph | Выбрано: `s_`, default entry, `all-sites`, owner configured welcome |
| D12 | CSS | Local UI unrestricted owner CSS; full embed theme tokens + saved theme предложены; arbitrary CSS не MVP |
| D13 | Fork Markdown roots | Включено по запросу; manifest/proof/preview/id namespace предложены в ROOT-IMPORT-V1 |
| D14 | Open lore | Решено: свой entry в shared space, не отдельный world; editing ACL independent |
| D15 | Donation/tariffs | Позже wallet link; quotas сейчас как architecture, цены и billing отдельно |
| D16 | Правки и уведомление поддержавших | 23.10 владелец подтвердил: поддержка версии, новая требует подтверждения; старый вес не переносится. Version-bound support/уведомления реализованы; Git-обновление переносит поддержку автоматически по последующему решению владельца |
| D17 | Ссылка на слово-смысл | 23.10 подтверждено: ссылка и поддержка — разные действия; автоматического голоса нет |
| D18 | Географическая модерация | Идея владельца на потом; MVP авторство/явные роли, без proximity ACL |
| D19 | Свой коренной набор/старт каждого входа | Требование 22.10: облако/индекс/карта из собственных Git-корней; профиль входа предложен, общий граф не разделяется |
| D20 | Авторство без собственного сайта | Требование 22.10: аккаунт одной БД пишет/голосует во всех её входах; site ownership не gate, один общий голос |
| D21 | Сеть независимых серверов | Подтверждено 22.10: отдельные регистрации, влияние не переносится; публичные ссылки/подписки на точки любых доменов; сетевой протокол ещё проектируется |
| D22 | Пользовательская синхронизация | Требуется: отдельные регистрации, пользователь выбирает peer-серверы, sync подписок/отображения своих постов; публичный профиль доступен без разрешения на sync; одноразовое приглашение/двустороннее подтверждение предложены, credentials/роли/влияние локальные |

Следующему исполнителю достаточно P00 и transport/auth/theme contract. Не
спрашивать заново, нужен ли Supporter или изолированный lore world: ответы
получены. Спорную формулу обсуждать на fixtures, а не назначать во время CRUD.

## 16. Передача и состояние

### Начало следующей сессии

1. Прочитать этот план редакции2, API-V1, EMBED-V1, ROOT-IMPORT-V1 и общую
   project card. Проверить AGENTS, origin/status, remote branches, очереди.
2. Сверить Progress с кодом: все будущие routes/tables/CLI в документах — target,
   а не уже существующий сервис. Статический navigation fix отдельный commit.
3. Взять один packet с dependent decisions/tests; future code references не
   команды для копирования в production. Не исполнять FIRST-PUSH/publish helper.
4. Не разделять граф по site_id и не создавать отдельную lore DB/world. Site
   ownership/provenance/квоты нужны, но scope редактора не граница смысла.
5. Feature branch `f-YYYYMMDDHHMMSS-two-words`; exact staging; preserve user work.
   Registered worktrees только `.worktrees/<repo>/` или `/tmp`, clean removal
   после опубликованного handoff. Ни protected merge, ни deployment без запроса.
6. Validate supported checks/diff; обновить Progress и contract docs. Handoff:
   exact commit, commands, tests actually run, open decisions, next packet.

### Готовая постановка следующему агенту

> Продолжи NODE06 по docs/IMPLEMENTATION-PLAN.md редакции2. Это общий сервис
> вики для сайтов Neocities Free: `s_` entry points в одном shared graph,
> bridge и full iframe, hosted frontend Amsterdam, fork Markdown roots и
> будущая lore wiki в том же графе. Прочитай EMBED-V1/API-V1/ROOT-IMPORT-V1,
> общий контекст и инструкции. Выполни только P00: локальный прототип двух
> origins с точным CSP, bridge/full embed и theme tokens, проверка auth handoff
> без выдачи global credential parent. Используй synthetic API и данные,
> проверь поддельные сообщения, reload/timeout и блокировку storage. Не
> внедряй geometry/платежи, не публикуй на сервер и не покупай Supporter.
> Запиши фактические результаты и ограничения, подготовь P01.

### Progress

| Область | История и текущий статус |
|---|---|
| Исследование исходника | 23 root points/35 edges, browser UI, API и общий лор проверены 12.09 |
| CSP | Direct external fetch запрещён, external frame разрешён; HEAD повторён 13.09 |
| Header/H1 → `/` | В main: общий вход, канонические адреса без языкового shell; browser regression |
| План редакции2 | Сервис/sites/bridge/full/hosted/fork/styles/quota/lore, edits/inbox/search handoff подготовлен |
| Проверки редакции2 | 5 Markdown files / 20 local links / 4 JSON examples; diff check; общий context validator 136 Markdown и 17 queue records. Runtime в этой правке не менялся |
| P00 bridge/full transport | Локальный synthetic prototype готов в `prototypes/embed-p00/`: два origin, CSP, handshake, typed read/theme, reload и write boundary. Не deployment и не real-Neocities proof |
| P01 backend bootstrap | `pyproject.toml`, FastAPI service, Alembic bootstrap migration, `/api/v1/{health,ready,meta}` и local tests готовы. Нет domain tables/API, hosted renderer или deployment |
| P02 site registry | Lifecycle + PostgreSQL/TLS acceptance; HTTP управление/renew/budgets добавлены P03b; release/transfer ещё не exposed |
| P03a | Регистрация/вход/logout/me, аварийный код, first-party `/account/`, secure cookie/CSRF и PostgreSQL limits; остальной P03 ниже |
| P03b | Owner-only create/list/manage/renew/verify/settings API, общие verifier slots/deadline, version preconditions и immutable welcome history; UI добавлен P03c |
| P03c | `/sites/` UI, hosted/game-lore вход, общая public projection, read-only iframe и theme; подготовлен отдельный manual deploy target |
| P03d | Public read bridge/SDK: site/point/search/capabilities, локальный HTTPS browser acceptance |
| P04a | JSON Schema, pure manifest/graph preflight и read-only immutable local Git CLI; owner source proof/transport/DB preview/accept implemented by the later Git-source packet |
| P04 operator publication | Accepted immutable Git roots/provenance/retirement and manifest home already in main; owner-managed public GitHub proof/transport/private preview/accept implemented in GIT-SOURCES-V1 |
| P05a public reads | Current point API, indexed full-body prefix search and bounded neighbor pages; authoring, voting, UI/bridge are implemented by subsequent packets. See [contract](PUBLIC-POINTS-V1.md) |
| P03 remainder–P14 | Scoped embed grants/consent, private/external-pin imports, sync/tariffs ещё впереди; public owner imports implemented; content purge implemented; scoped bans/quarantine implemented; operator imports and T1/social geometry implemented |
| Shared static field, 21.10 | Удалены ошибочные языковые shell и фильтр соседей; единые адреса/ленты, совместимые redirect и browser regression для всех 51 roots |

P00 evidence 13.09: Node protocol tests, Python compile и static build прошли;
в Chromium parent CSP заблокировал direct external fetch, bridge вернул точку,
применил допустимую тему, отверг CSS-like payload и write intent с
`AUTH_CONFIRMATION_REQUIRED`; reload создал новый handshake. Проверены заголовки
локальных parent/embed: `frame-src` у parent и точный `frame-ancestors` у child.
Не доказаны real Neocities, PKCE, storage/cookie/popup policy, origin revocation,
multi-frame и полный iframe renderer — это остаётся P03/P08/P12.

P01 evidence 13.09: exact pinned dependencies поставлены в isolated `.venv`;
`pytest`, Ruff, format check, static build и P00 protocol tests прошли. Alembic
создал `schema_metadata` и `alembic_version` в свежем временном PostgreSQL 18;
`/ready` дал 503 без DB и 200 после migration. Временный кластер остановлен;
это не production. Контрактная таблица users/sites/points начинается
только с P02/P05, не подменяется bootstrap marker.

P02 partial evidence 15.09: добавлена `0002_site_registry` с users/points/revisions,
sites/members/claims, undirected edges+claims и events; `all-sites` bootstrap projection;
internal `SiteRegistry` создаёт pending site, проверяет fixed-file HTTPS proof в две
транзакции и атомарно активирует site↔all-sites; public `GET /sites/{id}` читает только
active site. Claim mutations не опубликованы без P03 auth. Unit tests (SQLite только
для service logic, не как замена PostgreSQL), proof validation, Ruff, static build,
P00 protocol tests и offline PostgreSQL Alembic SQL прошли. Реальный PostgreSQL для
`0002`, concurrent verify/reclaim race и live DNS/TLS verifier остаются обязательной
приёмкой P02 перед закрытием пакета.

Предыдущий план single-site/API-only сохранён историей Git, не является
действующим target. Текущая реализация ограничена P00–P01 и частичным P02; production не менялся.

P02 hardening 21.10.2026: expiry проверяется заново после I/O; блокировка сайта,
отключение/смена владельца, смена origin/challenge во время fetch не допускают
активацию. Повторная verify активного сайта идемпотентна, inactive не оживляется.
Нормализация origin отвергает control characters, плохие DNS labels, multicast и
scoped IPv6; TLS socket закрывается, IPv6 Host корректно заключён в скобки.
Исправлен Alembic ConfigParser для percent-encoded URL. ORM index приведён к
существующему unique partial index миграции; новая миграция не нужна.

Добавлены изолированные PostgreSQL tests (real psycopg/Alembic 0001→0002,
downgrade/re-upgrade, duplicate origin, simultaneous verify/replay, две site points,
конкурентные изменения состояния, expiry, failed attempt и запрет takeover) и
локальные HTTP/TLS tests с временным сертификатом. DNS и destination управляются
fixture, проверка TLS и HTTP настоящая; это не live-Neocities E2E. CI получает
одноразовый PostgreSQL 18; инструкция запуска — `backend/README.md`.
Локально: 47 pytest passed (включая 11 PostgreSQL cases), Ruff check/format,
offline Alembic SQL, static build 51 roots и P00 protocol tests passed.
Python 3.14.4 / PostgreSQL 18.6, dialect `postgresql+psycopg`; asyncpg здесь не
используется. GitHub Actions с Python 3.12/PostgreSQL 18 прошёл для кода `df3f0bd`:
[run 39587505852](https://github.com/wratixor/node06/actions/runs/39587505852).
Static build и backend checks успешны; Neocities deploy пропущен на feature ref.

На завершении P02 HTTP управление было отложено до auth и verifier budgets.
Вход/восстановление добавлены P03a, управление и budgets — P03b ниже.
Release/transfer и scoped embed grants по-прежнему не реализованы; готовность
всего P03/social layer/Amsterdam deployment не заявляется.

P03a, 21.10.2026: владелец согласовал аварийный код вместо email/SMS. Код
показывается один раз при регистрации; восстановление атомарно меняет пароль,
перевыпускает код и отзывает все сессии. Добавлена migration `0003_account_sessions`
(Argon2id password hash, random session/recovery digests, durable auth counters).
Первичный интерфейс `/account/` использует HTTPS, no-store/frame denial, HttpOnly
cookie, exact Origin и CSRF. Регистрация — 201 только при успехе, 409 не успех;
поля сохраняются при ошибке, после регистрации имя остаётся для входа.
Подробности и ограничения — в AUTH-V1; это first-party, не выдача bearer родителю.
Локально 63 tests passed, Ruff/format, offline SQL и online psycopg migrations
0001→0002→0003/downgrade/re-upgrade, static 51 roots и P00 protocol passed.
Chromium HTTPS smoke (390px) прошёл для регистрации/входа/восстановления/logout,
конфликтов регистрации и симуляции отсутствующей cookie; физический mobile и
Neocities embed этим не проверены. Argon2id: 137–140ms/hash локально, 64MiB,
два одновременных hash slots на процесс; host budget перед deploy измерить отдельно.

Исправление общего поля, 21.10.2026: обнаруженное поведение «только текущий язык»
противоречило решению владельца и удалено вместе с переключением UI по языку
точки. Все связи до depth 2 отображаются независимо от `lang`; совпадающие seed
координаты получают только display separation без слияния ID и изменения seed.
Канонический адрес — `/?p=<id>&open=<id>`, общие `/recent/` и `/about/`, старые
языковые адреса — только redirect. `lang` описывает текст для accessibility.
Chromium regression `scripts/check-static-navigation.cjs` проверяет все 51 roots,
точный состав depth-2 соседей, переходы RU↔EN/back/forward, третью язык-точку
без пары, общие ленты, старые ссылки, NODE06→welcome, overlay close, WASD и
390px viewport. Сборка, JS syntax и P00 protocol прошли. Это локальная проверка;
публикация на Neocities требует отдельного merge владельцем.
Remote CI для кода `b35ecd0` прошёл: [run 39609565534](https://github.com/wratixor/node06/actions/runs/39609565534),
static build/backend tests/lint/migrations; deploy пропущен. Последующее изменение
28 подписей «version / версия» на «Point in English / Точка на русском» проверено
повторной сборкой и тем же полным browser regression, ID/связи сохранены.

P03b, 22.10.2026: сохранённая заготовка восстановлена поверх `origin/main`
`852e6f7` (merged fixes навигации и favicon). Добавлены authenticated owner-only
create/list/manage/renew/verify/settings HTTP routes; точный контракт и лимиты —
SITE-MANAGEMENT-V1. Сессия/owner проверяются внутри транзакций до и после fetch;
renew заменяет ID/digest challenge, settings требуют версии настроек и welcome.
Изменение текста создаёт immutable revision, no-op ничего не дописывает.
Theme — только allowlisted tokens. Языковых версий/пространств не вводится.

Migration `0004_verifier_leases` ограничивает общий admission нескольких workers.
Spawned child с deadline оборачивает DNS/TLS/body, родитель останавливает и
reaps зависший процесс. Account/IP limits и attempt budget хранятся в PostgreSQL;
global overload не расходует попытку. Local full suite: 79 passed; дополнительный
тест inactive/Git-owned welcome и изменённые случаи прошли focused run (6 tests).
Ruff/format, offline SQL, online 0003→0004 и downgrade/re-upgrade, static 51 roots,
JS syntax/P00 protocol прошли. Chromium HTTPS 390px проверил реальную cookie,
register/login, create/read/edit/409 stale/renew/list и CSRF rejection. Proof
activation проверена HTTP/PG fixtures + local TLS transport; real Neocities и
Amsterdam не проверялись, production migration не применялась.
Remote CI для кода `1756524`: [run 39726519414](https://github.com/wratixor/node06/actions/runs/39726519414)
успешен — Python 3.12/PostgreSQL 18, **80 passed**, Ruff/format, migration SQL и
static build. Deploy на feature ref пропущен. Ветка доставки:
`f-20261022080056-site-management`, target `main`; последующий docs-only commit
записывает evidence и уточняет код rate-limit ошибки `AUTH_RATE_LIMITED`.

P03c, 22.10.2026: база `origin/main e90a41a` включает merged P03b. Добавлены
`/sites/` owner UI с proof download/renew/verify, сохранением ввода при ошибке
сессии/409 и явным сравнением серверной версии; UI умеет показать one-time proof
даже при отказе follow-up GET после 201. Hosted/game-lore `/`, `/sites/{s_id}/`,
public graph projection и отдельный read-only `/embed/v1/{s_id}/` используют
тот же renderer и текущие активные сайты. Настройка темы остаётся внутри
публичного shell; управление/аккаунт от неё изолированы. Языковых версий нет.

`wiki.geno-dice.com` + `embed.geno-dice.com` используют один backend/DB. Private
API/UI закрыты на embed host, cookie host-only; frame-ancestors — exact verified
parent + trusted management preview. Storage denial не ломает чтение. Это не
PKCE/grants и не authenticated iframe: записывать через iframe пока нельзя.
Публичный read-only bridge добавлен отдельным следующим пакетом (ниже).
Static roots пока читаются из build projection; P04 importer не реализован.
Site/directory координаты null/display-only, social math не подменяется seed.
Public graph имеет explicit cap 200 active sites с 503 вместо silent truncation.

В `geno-dice-deploy` подготовлен отдельный explicit Amsterdam target `node06`
без таймера, проверка psycopg env/двух origins, резервная копия до изменений,
видимые migrations, runtime permissions только venv/dist и HTTPS/state gates.
Первый deploy и оставшиеся operator gates — [AMSTERDAM-FIRST-DEPLOY.md](AMSTERDAM-FIRST-DEPLOY.md);
полный runtime/read-only контракт — [HOSTED-WIKI-V1.md](HOSTED-WIKI-V1.md).
Локальный полный suite: 90 passed; после добавления config/error cases — focused
13 hosted checks. Wheel собран/установлен во временный runtime; Chromium HTTPS
390px проверил реальные формы, 409/session drafts, proof download, post-create GET
failure, public graph, реальный iframe preview, theme, blocked storage и отсутствие
cookie в фактических embed requests. Static browser regression прошёл для 51 roots.
Deploy tests прошли; Nginx/systemd templates проверены с локальными substitute
paths/certificates/high ports, не на production. Сервисы/DNS/сертификаты/БД production
не менялись. Код `ac14f27` опубликован в `f-20261022083906-hosted-wiki` (target `main`).
Remote CI: [run 39737812411](https://github.com/wratixor/node06/actions/runs/39737812411)
— success, PostgreSQL suite **93 passed**, Ruff, static/protocol и wheel packaging
прошли. Neocities deploy job на feature branch пропущен по условию workflow;
серверное развёртывание не выполнялось.

Следующий практический этап: review/merge двух исходных веток, свежая inventory
Амстердама и первый явный тестовый deploy по operator runbook. Затем real
Neocities/browser acceptance и scoped embed auth/PKCE/consent/bridge. До votes
обязательны notifications/revision-bound support; P03 целиком ещё не завершён.
Public onboarding широкой сети, origin release/transfer и автоматическое занятие
чужого origin не включать как побочный эффект тестового запуска.

## 17. Предложения по развитию

- **Веб-кольцо с памятью:** «Все сайты» — общий каталог живых входов. Кнопка
  «соседний сайт» ведёт по явной связи и сохраняет внешний адрес владельца.
- **Один вклад — много окон:** одинаковая мысль видна на нескольких сайтах под
  разным оформлением, сохраняя ID/автора/историю, без копирования сообщений.
- **Проверяемое происхождение:** карточка root с ссылкой на Git commit и source
  owner; official lore source узнаваем, не превращая соседние мысли в канон.
- **Переносимость:** site owner может выгрузить settings/welcome/свои roots;
  пользователь — свои тексты/действия. Чужая общая база и credentials не export.
- **История эпох и объяснение влияния:** snapshots и «куда ушла моя единица»
  делают смысл эксперимента наблюдаемым; без hidden votes и fake participants.
- **Локальный блокнот посетителя:** opt-in device drafts; owner сайта не получает
  доступ к чужой общей сессии. Сохранённый draft не равно опубликованная point.
- **Честная экономия:** quota dashboard и ограничения дорогих imports раньше
  платёжной системы. Тариф оплачивает серверные ресурсы, не место в истории лора.

Полноценная hosted-вики одновременно служит демонстрацией, fallback для
ограниченных браузеров и основой full embed. Это уменьшает число отдельных
клиентов, которые команде пришлось бы поддерживать.


P03d public bridge, 22.10.2026: отдельный маленький transport iframe
`/bridge/v1/{site_id}/`, bounded same-origin public read endpoint и SDK,
который владелец копирует на свой статический сайт. Реализованы только
`site.get`, `point.get`, `points.search`, `capabilities.get`; общий hosted graph,
без языкового разделения. Exact source/origin/channel/envelope, отказ от extra
params/arbitrary URLs/writes, 8 in-flight, deadlines, повторная проверка active
site на каждом read, credentials omit/storage-free, закрытие SDK при reload.
В `/sites/` появился URL посредника рядом с кодом полного iframe.
Контракт, рабочий пример и ограничения: `docs/PUBLIC-BRIDGE-V1.md`.
Это не scoped embed auth/PKCE/consent и не завершённый социальный API. Новых
миграций или изменений proxy/production нет. Обновление toolkit пользователем
не доказывает установку этого нового application packet. Следующий gate:
доставка application source и реальный Neocities Free acceptance, затем
scoped grants/consent/semantic editor/social writes по оставшемуся плану.

Проверено локально: полный PostgreSQL suite **96 passed**; Ruff/format, JS syntax,
P00 protocol и Alembic offline SQL прошли. Installed-wheel Chromium HTTPS fixture
прошёл: реальные typed reads/search через SDK при CSP connect-src self, rejected
writes/arbitrary params/spoofs, reload cleanup, blocked storage и отсутствие
global cookie на embed requests. Live Neocities и фактический сервер не проверены.


Уточнение 22.10.2026: [входы, корни и сеть серверов](ENTRANCES-ROOTS-NETWORK.md)
расширяет P04/P08 собственными root-наборами/стартами, P05 — явной приёмкой
автора без сайта. Независимые серверы и межсерверные ссылки вынесены в отдельный
будущий пакет; это не завершённая федерация и не автоматическое объединение БД.

Дополнение владельца 22.10: межсерверного переноса влияния **нет**, регистрации
отдельные. Подписки на публичные внешние точки не являются голосами и не требуют
account-sync доверия. Предусмотреть опциональную синхронизацию аккаунтов между
доверенными экземплярами; scope/защита/приёмка записаны в
[ENTRANCES-ROOTS-NETWORK.md](ENTRANCES-ROOTS-NETWORK.md), детали помечены предложениями.
Это план будущего сетевого пакета, без изменений работающей БД/авторизации.

Уточнение 22.10: пользователь сам настраивает peer-серверы, на каждом уже имеет
аккаунт. Синхронизируются подписки и отображение своих постов; публичный просмотр
профиля не требует разрешения на sync. Ссылка с ключом — предложение приглашения,
не постоянный секрет в публичном профиле. Подробный flow, границы scopes, источники
авторства, удаления/offline и приёмка — в ENTRANCES-ROOTS-NETWORK. Действующая
авторизация/БД не меняются этим документом.

P04a, 22.10.2026: реализованы структурная schema manifest, чистый validator
недоверенных blobs, stable namespaced IDs/site welcome, bounded inline Markdown
links и external revision pins, детерминированный candidate/meaning digest,
read-only локальный Git adapter/CLI. Пример корней — `examples/root-source`,
контракт/границы — `docs/ROOT-PREFLIGHT-V1.md`. Это не source ownership proof,
публичный импорт или запись в БД. Новых migrations/HTTP routes/runtime config нет.
Следующий пакет — source registration/proof, GitHub transport и persisted private
preview/atomic accept с core revisions и edge provenance; затем entrance root sets.

Проверка P04a: 142 local PostgreSQL-backed tests passed (46 новых root fixtures),
Ruff/format, static build 51 roots, P00 protocol, installed-wheel CLI/schema и
committed bilingual root example прошли. Это локальная проверка, не импорт
в production. Source proof/accept/retirement и UI подключения остаются P04b+.

P05a, 22.10.2026: current-only public reads/search/neighbors over static core and
accepted DB revisions. Migration 0008 normalizes Unicode search text and builds
a GIN index; online upgrade required. No history or draft leaks, fabricated core
revision IDs, social writes or change to legacy bridge search. Next bounded task:
bridge/picker integration; self-service imports and D16/D17-gated authoring/support
remain unfinished. Future repository devlogs: [DEVLOG-PLAN](DEVLOG-PLAN.md).

P05a validation: full disposable PostgreSQL suite 188 passed; after the final
accepted-digest consistency fix, the seven public-point tests were repeated.
Coverage includes current-vs-stale/draft visibility, full-body Unicode prefix
search, source retirement, orphan edge claims, page cursors/limits, response
budget, unavailable configuration and populated online migration down/up. Ruff,
format, 51-root build, P00 protocol, JS syntax, offline SQL generation and local
document links checked. Offline migration SQL intentionally contains a stop for
the Unicode backfill. No new browser UI or production deployment was performed.


P05b, 23.10.2026 (source): additive `points.searchPage`/`point.read`/`point.neighbors`
bridge methods reuse the P05a current-only store; legacy methods are preserved.
Shared header search/picker works with hosted API, full iframe same-origin bridge
and static-site postMessage SDK. It previews plain text and copies a web address;
future editor onSelect receives current revision/digest without creating links,
votes or posts. Static map remains local; shared external points open in the
hosted entrance. Connection settings: static/connection.json, existing Neocities
site ID reused. Contract and rollout: [PUBLIC-BRIDGE-V1](PUBLIC-BRIDGE-V1.md).
No auth/CORS/proxy/migration/endorsement changes. Authoring, self-service import
proof/transport, trust and notifications remain unfinished. Devlogs remain deferred.

P05b checks: 190 full PostgreSQL tests passed, 27 targeted public/hosted checks;
Ruff/format, 51-root build, JS syntax and P00 protocol passed. Installed-wheel HTTPS
browser checks passed on hosted, full iframe and static-parent picker, including
stale responses/failure recovery, safe text, current selection metadata, Escape,
CSP/source/channel/cookie boundaries and 390px/1440px visual inspection. Local
Chromium fixture alone grants its localhost origin loopback-network permission;
production/browser policies are unchanged. Real Neocities publication remains
unverified. No schema/service configuration or production write was performed.


P05c, 23.10.2026 (source): first-party `/editor/`, authenticated own-point create/
edit, explicit publication registry, version/digest-pinned semantic links, immutable
published history, actor-scoped idempotency and reciprocal shared graph projection.
Users need no site. Core stays honest (null revision + stored static snapshot).
See [complete contract and social continuation](POINT-AUTHORING-V1.md).

New owner direction: anyone may propose one replacement in a rolling 24 hours
across the instance; notify subscribers and their feed, compare old/new versions,
allow new subscribers to support a candidate, adopt after a majority. Later owner
clarification protects ALL Git-owned points, not only descriptions of the system. This is not implemented by authoring;
новые участники сначала подписываются на старую версию и могут выбрать новую;
в конце голосования new_influence > old_influence принимает правку; равенство
влияния оставляет старую, число людей не используется;
пределы срока 24 часа–7 дней, пустая точка без автопринятия. Do not conflate graph
links, revision support and proposal acceptance. The earlier Git/community-overlay
proposal is superseded: Git publication directly replaces its protected content,
automatically transfers active support and records a changelog/history. Community
voting applies to non-Git user points.

Подробная следующая постановка: [подписки, правки и уведомления](REVISION-PROPOSALS-PLAN.md).

P05c validation: 197 full disposable PostgreSQL tests passed (no skips), plus seven
repeated authoring/ACL/race/history cases after final header changes. Ruff/format,
static build 51 roots, protocol, JS syntax, offline SQL and documentation links
passed. Installed-wheel HTTPS Chromium passed creation without a site, selected-
word pinning, reciprocal graph visibility, lost-response retry without duplicate,
reload/edit and conflict draft retention, mobile layout, plus existing auth/sites/
bridge checks. Only pre-existing TestClient deprecation warnings remain. Live GET
verified deployed main `6b1b25e` (picker), not this new authoring branch. New migration
0009 must run through normal application deploy after owner review/main merge.

Header search UX, 23.10.2026: owner requested a simple JoyReactor-like input with
magnifier. Replaced the launch button/modal with an always-visible rounded search
field and anchored non-modal result dropdown. Enter/icon submit; typing debounces;
Escape/outside click dismiss results, preserving query/page. Arrow Down enters
results; semantic editor selection still returns current pins. Fits 390px/1440px,
including full embed and static iframe transport. CSS/scripts carry content-hash
query versions in static/hosted pages and the first-party editor, reducing stale
CSS/script mismatches after publication. No new API, schema, auth or deployment
configuration. 25 targeted PostgreSQL/hosted/authoring checks, installed-wheel
HTTPS browser flows (three transports, mobile bounds, inline field/magnifier,
keyboard/dismissal, failures and editor), build 51, lint/format, JS syntax and
P00 protocol passed. Screenshots inspected. Source feature only; no production
publication claimed by this change.


Governance clarification, 23.10.2026 (accepted design, not runtime): default vote
72 hours; one active proposal per user point. Author edits with active subscribers
also use voting. All Git-owned points (including game/lore and Git welcome) are
protected; authorized Git updates replace text directly, automatically transfer
active support and leave historical provenance plus changelog/news. No community
overlay on Git roots. User-version support still requires explicit confirmation.
100% of eligible subscribed influence permits immediate adoption, even before
24 hours, only with positive total subscribed influence fully covered by explicit
new-version ballots; silent positive influence also prevents early closure.
Zero-weight accounts do not block unanimity; zero total influence never adopts.
Headcount does not decide the outcome; no headcount quorum was approved. Scheduled range 24h–7d remains for
future configurable duration. Implement membership/choice/finalize races and
Git support transfer atomically; do not treat source updates as fresh user votes.
Canonical next packet: [REVISION-PROPOSALS-PLAN](REVISION-PROPOSALS-PLAN.md).


Influence-only correction, 23.10.2026: compare summed eligible influence for the
candidate/current version, not subscriber/voter counts. At 72h close new influence
must exceed old; equality retains current. Immediate 100% means positive subscribed influence fully covered by explicit
new-version ballots, not a count of consenting accounts or a share of cast ballots. Use one
consistent authoritative influence snapshot and preserve its identity in the
result. P05 subscription/proposal storage precedes P06 validated influence
snapshots, which must precede binding weighted adoption. T1 was subsequently explicitly approved for v1 with conservation checks.
The implementation uses fixed-point ballots and no headcount fallback.

Static NODE06 entrance also includes its Neocities profile link under the title:
https://neocities.org/site/node06 . Hosted tenant home replaces this static entrance
and does not inherit NODE06's profile link. This is source work, not publication.


Explicit-ballot clarification, 23.10.2026: subscriptions and ballots are separate.
Only influence behind explicit old/new votes cast during that proposal contributes
to its final totals. Nonvoters never become old-version votes. An explicit vote
atomically switches/creates subscription to the selected version, with one current
ballot per user/proposal and replay history. Initial old-version enrollment before
a new-version vote is not an extra ballot. Zero cast influence cannot adopt.
Owner confirmed the early denominator is ALL current eligible subscribed
influence. Early closure requires positive total subscribed influence and explicit
new-version ballots covering all of it. Silent positive influence blocks only
early consent coverage, never adds old-version votes to the scheduled tally.
100% of ballots cast so far is insufficient while positive subscribed influence
remains uncast.


### Implemented social packet — 23 October 2026

Migration 0010 adds revision subscriptions, daily proposals, explicit ballots,
trust, snapshots, durable private inbox/outbox and Git update provenance.
First-party `/community/` provides old/new comparison, support/voting, trust and
feed. The application worker runs every 30 seconds with a configured database.
P05 social storage + P06 influence foundation are implemented together; signed
point reactions, graph geometry, remote subscriptions/account sync remain next
packets. Deployment of this branch is not claimed. Full installed-wheel browser
check and disposable PostgreSQL tests validate the source. See SOCIAL-V1.

Every static copy now links to ACCOUNT, MY SITES, COMMUNITY and NEW POINT using
its public connection.json serviceOrigin. `/setup/` is built from
docs/SELF-HOSTING.md; hosted copies expose the same guide and use their own
management origin. Public frames link out to trusted management in a new tab.

### Contextual authoring / private favorites — 23 October 2026

Implemented source: field/search actions open a NEW related point on the configured
trusted management origin with the current source pin preselected. The editor's
inline tag lookup reuses the shared rectangular search component. Account-private
favorites (max64, migration0011) save point identities for subsequent use and
refresh their current pins when chosen. They never create support, votes or mass.
Detailed contract: POINT-AUTHORING-V1. Cross-server favorites synchronization and
rich-text/WYSIWYG editing are not introduced by this packet. Source validation
and production rollout remain separate states.

### Field social status — 23 October 2026

Implemented source: public influence/proposal state in field text panels and
shared search details, contextual first-party management links and first-party
own subscription/ballot display. Static Neocities and full frames use additive
read-only `point.social`; no account data crosses the parent/iframe boundary.
Per-point snapshot aggregates preserve current versus held mass and version pins.
Pending or older displayed texts do not inherit fresh labels. No geometry/radius,
weight formula or vote-policy change and no new migration. SOCIAL-V1 owns the
HTTP/pin/compatibility contract. Runtime read-only checks confirmed autodeploy
reached editor main9fc00b1 during this work; this new packet still needs review.

### Opposite-pair geometry and separate setup guides — 23 October 2026

Implemented source: six-coordinate/color profile, version-bound blocks, shared
T1 point-slot budget, anonymous batch projection, hosted/full/static field
integration and seed restoration. Links and support remain separate; blocks do
not cast ballots. Git authority transfers both reaction pins. Contract and
acceptance checks: SOCIAL-GEOMETRY-V1. Publication and live-site verification
remain separate steps after owner review.

Installation documentation is split into SELF-HOSTING.md (Russian, `/setup/`)
and SELF-HOSTING-EN.md (English, `/setup/en/`). These are documentation routes,
not language partitions of the graph. Shared field controls/links use English
without bilingual slash labels; first-party forms keep their own existing text.

Owner UI refinements in the same packet: replace verbose field support messages
with a four-icon subscribe/block/related-post/favorite toolbar and attribution.
Management-host actions are first-party writes; external embeds use explicit
trusted confirmation. Acknowledged editor create/edit opens the published point
in its hosted entrance, with validated local return paths. No draft is discarded
on failure or an uncertain write.


### Embedded drafting and compact profile — 23 October 2026

Implemented source packet: anonymous drafts over Neocities/full-frame maps,
explicit trusted top-level confirmation and return to the original point shell.
Static requested points are hydrated through the read bridge, so a newly created
post does not need a static rebuild. Migration0013 binds publication retries to
actor/site/content. First-party profile lists use compact tabs with direct
remove actions. Contract: [EMBEDDED-DRAFTS-V1](EMBEDDED-DRAFTS-V1.md).

Scoped authenticated embed grants, external own-point editing/favorites,
self-service Git source proof/preview/accept, semantic/diff UI refinement, devlogs
and remote profile/subscription sync remain subsequent packets. This creation
flow intentionally leaves public bridge read-only and account pages unframeable.
Publication requires normal owner review/main deployment and migration0013.


### Stat profile correction — 23 October 2026

Owner corrected the RGB-only profile editor: six independent positive coordinates
replace the three complementary sliders. The canonical root order is Body,
Spirit, Onslaught, Composure, Reaction, Technique internally; the public controls
show colors only, without naming the stats. Color is derived preview,
not an input or a new budget. Raw stored values and the existing1..65535 API
range are preserved; changing one component does not rewrite its opposite.
No new migration, coordinate model, influence or voting rule. See
[SOCIAL-GEOMETRY-V1](SOCIAL-GEOMETRY-V1.md).

The planned external own-point/favorite library extension remains next; no
implementation of that separate packet is claimed by this profile correction.


### Hosted wiki corner link — 23 October 2026

Standalone field pages always link their upper-left brand to the instance root
`/`, including when visiting another site's entrance. The title comes from the
configured default entrance's effective home page (Git manifest `home_page.title`
under Git/Auto), then its display name, then the operator title. An unrelated
tenant cannot replace the instance brand. Full iframe corners keep their own
entrance, and the Neocities static root keeps NODE06. Content home priorities,
points, languages and graph coordinates are unchanged; no migration.

Validation for the stat/corner correction:33 targeted PostgreSQL hosted/geometry
checks passed. Packaged-wheel HTTPS Chromium passed, including full-range raw
profile load/save, independent components, rejection of invalid values, color-only
markers, derived preview/social geometry, instance-root corner navigation and
unchanged static/full-frame corners. Ruff/format,51-root build, JS syntax,
protocol and diff checks passed. No migration or production write performed.


### Personal section navigation — 23 October 2026

Owner-requested compact composition: account, profile, sites and editor now share
one menu with a current-page marker. Navigation stays in the same tab except
editor sign-in, which preserves the draft in its original tab. Profile tabs include the
six-component color editor; section fragments survive reload and browser history,
with `#my-color` retained. Point version comparison is collapsible, and refresh
shares the profile heading row. The filter is hidden for color/trust forms.
Account recovery and session handling, editor return channels, private API
boundaries and influence rules are unchanged. No migration. The external library
extension remains planned. Contract: [EMBEDDED-DRAFTS-V1](EMBEDDED-DRAFTS-V1.md).

Validation:50 PostgreSQL hosted/auth/authoring checks passed. Final packaged-wheel
HTTPS Chromium flow passed, including consistent navigation/current-page markers,
editor sign-in draft-preserving target, mobile overflow checks on all four
personal pages, color deep links/legacy alias/reload/browser Back and normal
same-origin/external publication. Six raw components and color-only labels remain
covered. Ruff/format,51-root build, JS syntax, protocol and diff checks passed.
No production write performed; owner review/main deployment remains required.


### Radar, author profiles and trusted tag library — 23 October 2026

Owner-requested six-axis draggable color input replaces the default numeric form;
exact values remain collapsible. Fixed logarithmic display scaling covers the
existing raw range without altering color/T1 calculations. Mouse, touch and
keyboard operate each component independently. The field VIEW arrow buttons are
removed; the geometry refresh button is now in the field controls.

Post attribution now links a real user to a public author profile with visible
points, T1 subscribe/unsubscribe and explicit author blocking. Owner confirmed
that following an author equals T1 trust. Blocking removes outgoing trust and
hides their events/posts from the existing personal inbox; it does not mass-block
points, add negative trust or restore trust on unblock. Migration0014 adds only
personal author blocks. See [AUTHOR-PROFILES-V1](AUTHOR-PROFILES-V1.md).

The next external-library packet now implements trusted selection of own points
and favorite tags: a top-level private library exports only an explicitly chosen
public ID, re-read by the anonymous editor before linking. No authenticated embed
capability, external inline edit, automatic list export or third-party cookie.
Contract: [EMBEDDED-DRAFTS-V1](EMBEDDED-DRAFTS-V1.md). External inline own-point
editing, self-service Git source proof/preview/accept, diff refinement, devlogs
and remote profile synchronization remain subsequent work.

Acceptance — 24 October 2026: final full disposable PostgreSQL suite242 passed.
Populated0013→0014 upgrade/downgrade/re-upgrade preserved the published revision;
block/unblock, T1 edge removal, idempotent replay, CSRF/origin rejection, inbox
filtering and retained point subscriptions passed. Final installed-wheel HTTPS
Chromium passed mouse/touch/keyboard radar input, independent/full-range raw
values, profile links/T1/block controls, selected-only private library export,
wrong-source rejection, two-link external publication with lost-response retry,
mobile layout and absence of global cookies on embed requests. Ruff/format,
51-root build, JS syntax, protocol and diff checks passed. No production write.

Normal deployment applies0014 using existing `alembic upgrade head`; Nginx already
proxies the wiki's routes and needs no new exception. External inline own-point
editing remains planned. Source readiness does not establish live deployment.


### Creation feed and compact color — 24 October 2026

Лента теперь означает только создание новых точек от доверенных авторов или
с исходной связью на подписанную точку. Редактирование не поднимает пост.
Текущие подписки позволяют отматывать историю по непустым дням UTC; уведомления
о версиях отдельно. First-party read API, actor-bound keyset, migration0015
(index only); anonymous embeds открывают доверенный профиль, без private export.
Диаграмма уменьшена до230px, область залита текущим вычисленным цветом;
шесть независимых значений и расчёты T1/геометрии не изменены.
Контракт: [CREATION-FEED-V1](CREATION-FEED-V1.md).

Решения по областям модерации, 30-дневному удалению с ID, общему карантину
забаненных, Git-политикам, баннеру/поддержке и синхронизации записаны в
[MODERATION-PLAN](MODERATION-PLAN.md). Эти функции остаются запланированными.

Acceptance: PostgreSQL feed filters/history/cursors, private access, point/author
blocks and populated0014↔0015 roundtrip passed. Initial full245-case backend run
found four SQLite schema failures from PostgreSQL C collation; index DDL was
restricted to PostgreSQL like the existing search index. All13 affected/new
regressions then passed (including the extra access case;246 cases now collected).
Installed-wheel HTTPS Chromium passed the creation-feed section, unchanged
revision notifications, static-origin private-read exclusion,230px radar and
computed polygon fill, plus the existing authoring/bridge/cookie isolation flow.
No production writes or authenticated embed grants.
Static Chromium regression also passed all51 roots, shared multilingual
neighborhoods, canonical/legacy URLs, setup language links, feed handoff,
overlay close and WASD. Ruff/format, JS syntax, protocol and diff checks passed.


### Scoped moderation first packet — 24 October 2026

Реализованы делегированные moderator/admin для server/site, собственник активного
сайта как администратор его области, отдельная доверенная панель жалоб и флаг
в карточке точки. Уникальные заявители увеличивают один случай, без fanout
в inbox. Решения об обратимом скрытии/восстановлении и ролях атомарны,
идемпотентны и аудируются; bootstrap server-admin только оператором по ID.

Общий фильтр закрывает backend static fallback, hosted/public reads, поиск,
историю, bridge, geometry, feed и preview списков. Site-контекст выбирается
явно, серверное скрытие отменить выбором другого сайта нельзя. Независимые
файлы Neocities/чужие Git и кэши вне контроля сервиса. Миграция0016 добавляет
таблицы без переписывания публикаций. Clock серверного скрытия хранится,
автоудаление не включено. Баны/общий карантин, purge/tombstones и полноценная
пагинация всех причин/аудита — следующие пакеты.
Контракт и выпуск/откат: [MODERATION-V1](MODERATION-V1.md).

Acceptance: the full249-case backend run passed248 tests; its single failure
was an old graph-size mock accepting no site argument. Updated mock and all29
hosted/moderation regressions passed, including the additional Git reimport case
(250 tests now collected). Tests cover role revocation before replay, unique
reporters, site/server isolation, static-core fallback, read/history/geometry/
feed/bridge filtering, stable hide time in UTC, restore of retired sources and
populated0015↔0016 roundtrip. Offline SQL, Ruff/format, JS/protocol/diff passed.
Final installed-wheel HTTPS Chromium passed safe report rendering, point-to-panel
site context, lost-response idempotent hide/retry, other-site visibility,
restore, delegate/revoke controls and mobile layout, alongside existing editor,
profiles, full iframe, anonymous bridge and cookie isolation regressions.
Static Chromium passed all51 roots, shared neighborhoods, canonical/legacy
navigation, third-language fixture, feed, overlay and WASD. No production write.

### User discovery and influence rankings — 24 October 2026

Added `/directory/`: public active-user search, links to author profiles/posts,
user T1 rankings and positively supported current-version point rankings.
Reads reuse persisted fixed-point snapshots, bounded paging and fresh visibility;
pending snapshots do not show obsolete weights as current. Public output omits
registration dates, account state and private social edges. Scope-authorized
moderator search includes registration/state and explicit ID selection for the
existing role assignment form. Scope/status/button layout now uses an aligned
responsive grid. Personal and static service navigation expose the directory.
Contract: [DIRECTORY-V1](DIRECTORY-V1.md). No migration/T1 formula change.
Bans/quarantine and30-day purge remain the next moderation packages.

Validation: full253-case PostgreSQL suite passed; expanded directory tests also
passed anonymous search/privacy, literal wildcards,20+7 ranking pagination with
stable ties, scoped role revocation, pending/stale pins and static-root ranking.
Installed-wheel HTTPS Chromium passed anonymous directory → author/posts,
private registration/state search → explicit role target selection, aligned
scope/status/submit controls, responsive mobile pages and embed-host denial,
alongside prior editor/profile/moderation/bridge/cookie-isolation scenarios.
Static Chromium passed51 roots, canonical/legacy paths, third-language points,
feed, overlay and WASD. Ruff/format, JS/protocol and diff checks passed.
No production writes; publication follows owner review/merge and normal deploy.

### Field heading and toolbar correction — 24 October 2026

Hosted map headings now use the same instance/Git-home brand as the navigation
and return to `/`, including tenant point views. Embedded maps keep the tenant
name and iframe-local home. Static NODE06 headings remain NODE06. Escaped title
and both home links are covered by the existing targeted PostgreSQL test.
Field toolbar buttons, including geometry refresh, share a40px height; static
Chromium checks desktop/mobile dimensions alongside51-root navigation.
No schema, content or influence change; ordinary application/static deploy.

### Explicit inline link insertion — 24 October 2026

The editor action is now labelled «Вставить ссылку». It captures the selection
or empty caret before focusing point search. Choosing a point wraps selected
words or inserts its short label as `[text](md://point/id)` at that caret,
then places the caret after the markup. The point is declared once among links,
even when used repeatedly in the text. Changed drafts are not overwritten by
an old explicit insertion request; bracket/newline selections get a short error.
Ordinary tag selection without a text selection still only adds a graph link.
No new write API, influence or schema change; hosted/external editor share code.

Installed-wheel HTTPS Chromium passed selection wrapping, empty-caret insertion,
caret placement and one declared pin for repeated mentions, plus the existing
publication, external drafting, profiles, moderation and anonymous bridge flows.
The first added browser assertion selected an arbitrary matching result; the
final test targets the exact root ID and passed. JS/Ruff/format/diff checks passed.
No production change; normal app deploy after owner merge.

### Scoped bans and private quarantine — 24 October 2026

Implemented the owner-confirmed site/server restriction boundary. Moderators can
set/revoke block or quarantine, timed or indefinite, with role/session/CSRF checks,
receipts, reasons and audit. Publication rechecks under the graph lock before
receipt replay. The public filter suppresses user-authored points in the selected
scope. Quarantine captures newly created/edited posts; private cohort readers
are all actively banned users and assigned moderators in the applicable area.
Local membership/roles cannot bypass server quarantine or independent point hides.
Anonymous bridge/embed gains no private access. Editor preserves site context,
reports quarantine explicitly and links to first-party private reading.

Server ban expiry invalidates persisted projection freshness even without a new
event. Global T1 computation and revision decisions now use global visibility,
so local views do not change shared weights/outcomes. Source-managed roots and
base user influence remain intact. Migration0017, no new dependency/configuration.
Contract: [SCOPED-BANS-V1](SCOPED-BANS-V1.md). Next:30-day purge/tombstones;
self-service sources, federation and devlogs remain separate work.

Validation: full259 tests passed258, with one stale tenant-home link expectation
from the earlier instance-brand correction. Updated assertion and final25
bans/social/hosted cases passed. Follow-up3 clock/concurrency cases and2 epoch
cases passed (263 now collected,10 new ban tests). Parallel PostgreSQL proves
waiting transactions use post-lock wall time for quarantine; snapshot tests
reject expiry crossing computation. Populated0016↔0017 roundtrip passed through
production psycopg. Installed-wheel HTTPS Chromium passed ban/revoke UI,
quarantined editor output, authenticated cohort reading and other-site visibility,
XSS/mobile checks plus existing social/editor/bridge flows. Static51-root
regressions, Ruff/format, JS/protocol, offline SQL and diff passed. No production
operation performed. Existing deploy script upgrades Alembic before restart.


### 24 October 2026 — sphere actions menu

Sphere right-click opens a square 3×3 action grid sharing the viewer toolbar;
both include edit, with protected Git/system points disabled. Own point editing
uses the existing management overlay; proposals/external editing stay on the
trusted host. Native sphere tooltips no longer cover custom previews. Pending
reaction receipts are shared between both surfaces. No migration is required.

Validation: installed-wheel HTTPS Chromium passed the shared menu/viewer,
protected roots, overlay editing, lost-response retry between surfaces and
existing hosted/embed/profile/moderation flows. Static51-root checks passed at
1440px/390px, including square bounds, native-title removal, programmatic scroll
survival, wheel/Escape dismissal and no page overflow. A focused disposable
HTTPS check also passed Space activation/replay with explicit button focus.
JS/protocol, Ruff/format and diff checks passed. No production action performed.


### 24 October 2026 — public point clipboard

Copy-link and remembered public references share viewer/context actions. The
browser collection survives reloads, is registrar-scoped and transfers through
an origin/source/channel-bound editor overlay handshake. Bulk graph links and
inline semantic links refresh public pins before changing the draft; a missing
point never adds a partial set. URL paste resolves local IDs without fetching
an arbitrary URL. No new authenticated endpoint or database migration.
Contract: [POINT-CLIPBOARD-V1](POINT-CLIPBOARD-V1.md).

Next moderation packet was audited against current schema and writers:
[PURGE-TOMBSTONES-PLAN](PURGE-TOMBSTONES-PLAN.md). Automatic cleanup is not yet
implemented; the audit covers revision/search bodies, structured root snapshots,
proposal candidates, core fallback, imports and retained ID references.


Clipboard validation: storage/URL sanitation and quota/denial checks passed;
installed-wheel HTTPS Chromium passed URL paste, bulk semantic links, missing
point rollback, overlay collection removal and external parent transfer with
spoof rejection. Static51-root checks passed persistence after reload plus copy
success/denial fallback. Focused390px/1440px layout checks passed long labels,
inert HTML and a bounded64-item list. Backend Ruff/format, JS/protocol, build
execution and diff checks passed. Optional legacy build.py Ruff remains at the
same49 diagnostics as origin/main; no new diagnostics were introduced there.
No production change or migration performed.


### 25 October 2026 — permanent content cleanup

Migration0018 adds a permanent tombstone ledger and PostgreSQL resurrection
guards. The graph-locked worker cleans one eligible server-hidden point per pass
after30 continuous days, atomically clearing all revision/search bodies, proposal
text and structured root snapshots. Restore before cleanup cancels retention;
site hiding/bans do not start it. Public addresses open an empty marker; Git/core,
receipts and restore cannot refill that ID. Source Git/static copies and backups
remain outside this DB cleanup. Contract and rollout/rollback boundary:
[CONTENT-PURGE-V1](CONTENT-PURGE-V1.md). No production action performed.

Validation: focused cleanup8/8 on disposable PostgreSQL, online migration,
installed-wheel HTTPS tombstone/bridge and static51-root navigation passed. Full
DB-enabled run:267 passes plus4 old SQLite clock-fixture failures reproduced on
main; repaired test adapters passed8/8 in both affected modules. Final no-DB run:
118 passed/153 PostgreSQL skips (DB tests already exercised separately). Backend
Ruff/format, JS/protocol/clipboard and diff checks passed.

### 25 October 2026 — owner Git sources and multilingual home follow-up

Owner source registration, immutable GitHub transport, private preview/accept and
opt-in15-minute polling are the active implementation packet. Existing operator
sources retain their deploy authority. Source control requires account/site-owner
and repository proof; a manifest site ID alone grants no authority.

The owner requested a home-page redesign with JS-switched translations:
[HOME-LANGUAGES-PLAN](HOME-LANGUAGES-PLAN.md). Each home language selects its own labels **and link targets**, e.g. lore-ru vs
lore-en. Existing point IDs/URLs are preserved; the buttons deliberately navigate
to different independent points for each language. No graph locale partition.

Git source packet implemented: [GIT-SOURCES-V1](GIT-SOURCES-V1.md), migration0019.
Full backend run292 passed; final focused source cases, online migration/rollback,
installed-wheel HTTPS UI, lost-response accept, mobile source preview, static51-root
navigation, build, protocol/clipboard and Ruff/format passed. The GitHub loader
also read the real public wiki commit without writes. Production remains unchanged.


### 25 October 2026 — complete home translations

Implemented the accepted [home-language packet](HOME-LANGUAGES-PLAN.md): full
HomePage variants in owner settings and Git manifest, bounded across the entire
bundle, with local aliases resolved in every translation. The same script-free
renderer serves hosted, read-only iframe and static home. JS changes a whole
variant including its point destinations and HTML lang, with per-entrance local
preference, browser-language fallback and usable default HTML without JS.
The owner editor keeps unsaved variants when switching and preserves source
priority and settings-revision conflicts. Existing independent graph IDs, edges,
semantic digests and vote/support rules are unchanged. No new migration.

Static NODE06 includes separate ru/en home variants; other content manifests
need their own explicit translations after the engine update. No automatic
translation pairing or production publication is implied.

Validation: full disposable-PostgreSQL run309 passed; final focused86 passed
including the two added size/language-boundary cases and the final compatibility
validator. Full installed-wheel HTTPS acceptance, owner language editor,
third-language/default/no-JS/storage-denial/embed/mobile cases, static51-root
navigation, build, JS syntax, protocol/clipboard and backend Ruff/format passed.
No production deployment. Existing builder-wide lint debt remains outside this
packet; changed new Python sections add no lint diagnostics.


### 25 October 2026 — NODE06 repository devlogs

The first [devlog packet](DEVLOG-PLAN.md) adds four RU/EN stage pairs and an index
pair covering shared space, Neocities/iframe integration, repository roots/home
and independent server setup. Static home now links to the correct language's
index. Core build validates all reciprocal links and explicit seed coverage;
new neutral display seeds do not change existing point IDs or coordinate entries.
Public technical claims are grounded in source29135cf and maintained contracts;
no private deployment data or new lore is published by these files.

The existing UI-managed Neocities entrance remains; these are static/core content
files, not a new tenant Git import. Merge/build/static publication and backend
update are separate release actions. Godot devlogs remain the next scoped packet.

Validation: build61 passed reciprocal links and exact coordinate coverage;
previous seed entries are unchanged. Chromium passed all61 root neighborhoods,
canonical/legacy links, independent third-language behavior, RU/EN home cards,
stage/index links and mobile reader. The full iframe snippet is escaped inert
text in both post projections. PostgreSQL hosted/home-language suite41 passed;
final projection check passed after prose edits. Backend Ruff/format,
protocol/clipboard and diff checks passed. Public Wiki home (earlier packet)
was independently verified through anonymous API/browser reads. No new devlog
publication or server mutation was performed.
