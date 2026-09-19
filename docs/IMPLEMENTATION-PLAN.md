# NODE06 — сервис общей вики для независимых сайтов

Статус: исследование выполнено; реализация бэкенда не начата.
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
с общей БД, пользователями, графом и расчётом влияния.

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
- Сейчас пересобирается план; сервер, импортер, bridge, платежи не реализуются.

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
Социальная геометрия остаётся обязательной целью движка, поставляется после
надёжного сохранения/объяснения raw событий и массы.

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
| Геометрия | Версионированный Git-owned `content/root-coordinates-v1.json` даёт шесть начальных координат, проверяемых сборкой | Это исходная смысловая раскладка, не социальные измерения; публичная карта не подписывает оси |
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

**Права:** site owner меняет своё приветствие, источники и theme; автор меняет
допустимое им содержимое; operator осуществляет общую abuse moderation. Владение
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
points=0.5. Формула рекурсии ещё не определена. Ниже **кандидат T1**, который
нужно принять отдельной короткой ADR после проверки синтетическими сценариями.

Регистрация сайта, импорт Markdown, второе iframe и открытие того же пользователя
на другом сайте не добавляют base mass. Site points и Git roots — terminal sinks,
как обычные points. Каталог не передаёт массу всем сайтам.

Пусть N — число активных пользователей, `T[i,j]=1/(k_i+1)` для self и каждого
активного поддержанного человека. Иначе T=0. T row-stochastic.

```text
w(0) = [1, ..., 1]
w(t+1) = (1-d) * [1, ..., 1] + d * transpose(T) * w(t)
0 <= d < 1; начальный исследуемый d = 0.5
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
явно меняет распределение. Это предложение, требующее принятия вместе с T1.

Суммарная погрешность proposal ≤1e-9*max(1,N), L1 residual проверяется; максимум
итераций 500, non-convergence/NaN/negative result не публикуются. Обход ID
детерминирован; алгоритм/config/version/input digest сохраняются. Не округлять
до двух знаков на промежуточных этапах. Rounding — только UI.

Проверить N=0, isolated users, кольца, звезду, clique, asymmetric graph,
block/reactivate, remove trust, remove final point support, одинаковый input
в ином SQL order. Sybil-атака всё ещё добавляет N через новые аккаунты: сохранение
массы не доказывает независимость людей. Защита регистрации нужна отдельно.

### Публикация вычислений

Одна job фиксирует repeatable input на cutoff, считает trust→mass→geometry,
проверяет инварианты, пишет новый run и атомарно меняет published_run_id.
Читатель использует один run ID во всех derived полях. Error/crash оставляет
последний хороший run с отметкой устаревания. Proposal cadence 60 секунд,
degraded-after 5 минут; уточнить по замеру. Одновременные jobs не конкурируют.
Проверять удаление всех derived caches и полную пересборку. Не говорить, что
последняя реакция уже изменила карту, пока её event не вошёл в опубликованный run.

Старый run нельзя приписывать новому тексту: response сравнивает content revision
и при несовпадении отдаёт mass/geometry=null, calculation_pending=true. Историческая
масса показывается отдельно со своей версией, никогда как поддержка нового смысла.

## 9. Шесть координат и настоящий социальный движок

**Решено:** 6 чисел, не RGB; projection в 3 пары только в интерфейсе; цвет,
масса и confidence — независимые каналы. Complementary pairs:
cyan/red, magenta/green, yellow/blue. У текущего `relativeAxis` знак компоненты
и направление цветного луча требуют фиксированной таблицы и golden cases:
не переставлять индексы неявно.

**Открытая научно-продуктовая часть D05:** API не объясняет источник первых
user coordinates и точную роль opposition. Поэтому нельзя честно вывести
содержательную семантику шести осей только из текста текущего контракта.

Два кандидата для P07:

1. Добровольные self-anchors на трёх утверждённых шкалах; координата точки —
   нормированное взвешенное агрегирование supports, opposition отдельно даёт
   disagreement/confidence. Проще объяснить и стабилизировать; требует осознанно
   вернуть самоидентификацию из прежнего проекта. Названия старых полюсов не
   переносить без решения владельца.
2. Emergent layout из signed user×point reaction matrix: совместные реакции
   дают сходство, затем reproducible low-rank projection. Лучше соответствует
   идее возникающего поля, но оси не имеют готовых смысловых названий; есть
   rotation/sign ambiguity, cold start, чувствительность к кампании голосования.
   Нужны зафиксированный seed, alignment к прошлому run, privacy review и
   объяснение, что близость не является диагнозом или объективной истиной.

Рекомендация для первой социальной alpha: weights/mass включены,
`geometry.coordinates=null` до принятия и проверки одного из вариантов.
На карте допускается только явно помеченная synthetic/unresolved раскладка.
Это этап поставки, не отмена социальной геометрии целевого движка.

Для любого выбранного варианта определить: допустимый диапазон 6 чисел,
нормализацию пары, zero/epsilon, continuity, confidence formula, минимальные
данные, авторский seed/его отсутствие, влияние opposition, устойчивость между
срезами и объяснимость. Хранить space_version и algorithm_version отдельно.
Confidence не называть вероятностью истины. Низкий sample/конфликт не скрывать.
Старый порог «закрепление с четвёртого сторонника» — вопрос, не default.

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
- `/en/`, `/ru/` сохраняются как совместимые shell входы; любой `p` открывает
  любую общую public point. Нет translation_group и языковой изоляции графа.
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
| P07 | P06,D05 | Geometry prototype/approved formula | Six values, cold start, opposition/confidence, cross-site layout consistency, no false certainty |
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
| D03 | Смысл support/oppose и T1 formula | Исходный API + проверяемый кандидат §8; коэффициент ещё не принят |
| D04 | Автор редактирует свои точки и ссылки | Новое требование отменяет общий create-only запрет; чужие пары/источники недоступны |
| D05 | Social coordinates | Self anchors vs emergent layout, требуется prototype/owner review |
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
| D16 | Правки и уведомление поддержавших | Требование принято; version endorsement/pending/held бюджет — предложение для утверждения до P05/P06 |
| D17 | Ссылка на слово-смысл | Поиск/ручной выбор нужны; separate support action предложен, автоматический голос не утверждён |
| D18 | Географическая модерация | Идея владельца на потом; MVP авторство/явные роли, без proximity ACL |

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

| Область | Статус на 13.09.2026 |
|---|---|
| Исследование исходника | 23 root points/35 edges, browser UI, API и общий лор проверены 12.09 |
| CSP | Direct external fetch запрещён, external frame разрешён; HEAD повторён 13.09 |
| Header/H1 → `/` | Source fix и browser/build verification выполнены, feature branch; main не изменён |
| План редакции2 | Сервис/sites/bridge/full/hosted/fork/styles/quota/lore, edits/inbox/search handoff подготовлен |
| Проверки редакции2 | 5 Markdown files / 20 local links / 4 JSON examples; diff check; общий context validator 136 Markdown и 17 queue records. Runtime в этой правке не менялся |
| P00 bridge/full transport | Локальный synthetic prototype готов в `prototypes/embed-p00/`: два origin, CSP, handshake, typed read/theme, reload и write boundary. Не deployment и не real-Neocities proof |
| P01 backend bootstrap | `pyproject.toml`, FastAPI service, Alembic bootstrap migration, `/api/v1/{health,ready,meta}` и local tests готовы. Нет domain tables/API, hosted renderer или deployment |
| P02–P14 | Не реализованы: site registry/import/auth/tariffs пока документы |

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

Предыдущий план single-site/API-only сохранён историей Git, не является
действующим target. Текущая реализация ограничена P00–P01 и не меняет production.

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
