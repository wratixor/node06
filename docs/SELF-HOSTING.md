NODE06: своя копия / Your own copy

Одна база объединяет пользователей и точки подключённых сайтов. Сайт — своя точка входа и оформление, а не отдельный аккаунт. Регистрация, создание точек и голосование доступны через доверенный сервер. Ссылки ACCOUNT, MY SITES и COMMUNITY открывают его отдельно: пароль не передаётся сайту, встроившему вики.

One instance shares accounts and points across its connected sites. A site has its own entrance and theme. Account, site management and community actions open on the trusted service; the embedding site never receives your password.

Режим 1 — статический сайт без сервера / Static only

Скопируйте или форкните репозиторий, установите Python 3 и выполните `python3 build.py`. Опубликуйте содержимое `dist/` на Neocities или любом статическом хостинге. Коренные точки хранятся в `content/`; связи `md://` должны быть взаимными. Языки принадлежат точкам, а не разным версиям сайта. Без подключённого сервиса останутся локальные коренные точки; общей регистрации и записи в БД нет. Чтобы убрать ссылки на чужой сервер в независимой статической копии, удалите `static/connection.json` перед сборкой.

Copy/fork the repository, run `python3 build.py`, then upload `dist/`. Edit Markdown in `content/`. Remove `static/connection.json` for a disconnected static copy.

Режим 2 — свой фронт + существующий сервер / Static frontend + shared instance

Зарегистрируйтесь на выбранном сервере, откройте MY SITES, добавьте HTTPS-адрес своего сайта. Разместите выданный файл `node06-verification.txt` в корне сайта и подтвердите владение. Скопируйте реальные `siteId`, `embedOrigin`, `serviceOrigin` в `static/connection.json`, пересоберите и опубликуйте `dist/`. Эти значения публичные: секреты и пароли в файл не добавляются. Главное меню автоматически ведёт на выбранный сервер.

Register on the chosen instance, add and verify your site in MY SITES, copy its public connection values into `static/connection.json`, rebuild and publish. Neocities Free reads shared data through the small iframe bridge; it does not fetch the external API directly. Your local CSS styles your own frontend.

[Подключение маленького iframe-посредника / Small bridge setup](https://github.com/wratixor/node06/blob/main/docs/PUBLIC-BRIDGE-V1.md)

Режим 3 — встроить всю вики / Full wiki iframe

После подтверждения сайта скопируйте готовый iframe из MY SITES в HTML своей страницы. Его адрес имеет вид `https://YOUR-EMBED-HOST/embed/v1/YOUR-SITE-ID/`. Содержимое iframe читает общую БД; вход и изменения открываются на доверенном сервере. CSS родительской страницы не проникает внутрь чужого iframe: используйте настройки темы сайта в MY SITES. Не ставьте внутрь iframe форму, собирающую пароль для передачи родителю.

Paste the full iframe snippet from MY SITES into your page. Use the site's theme settings for the framed wiki; cross-origin parent CSS cannot style its contents. Reading needs no third-party account cookie.

Режим 4 — своя размещённая вики и контент из Git / Hosted wiki + Git content

Если сервер уже работает, повторный backend не нужен. Подключите репозиторий контента к существующему сайту через операторский деплой. Manifest задаёт сайт, коренные Markdown-точки и главную с произвольными блоками/ссылками. Приоритет главной выбирается отдельно: настройки БД либо репозиторий. Пример структуры — `examples/root-source/`. Проверяйте снимок и публикуйте через штатный деплой, не правьте рабочую БД вручную. Точки из Git защищены от голосования; новый принятый снимок переносит их активную поддержку и публикует ченжлог.

Use a content repository for the roots and landing blocks of an existing hosted site. It does not create another account database. The operator validates and publishes an immutable Git snapshot through deployment.

[Публикация контента / Content deployment](https://github.com/wratixor/node06/blob/main/docs/OPERATOR-CONTENT-DEPLOY.md)

[Главная и приоритет источников / Home blocks and source priority](https://github.com/wratixor/node06/blob/main/docs/HOME-BLOCKS-V1.md)

Режим 5 — независимый сервер / Independent instance

Нужны HTTPS-домены для доверенной вики и отдельного embed-host, PostgreSQL и Python с зависимостями из `pyproject.toml`. Копия репозитория работает без доступа к исходному владельцу. Создайте виртуальное окружение, установите `.[dev]` для разработки либо собранный wheel для сервера. Настройте приватное окружение по `backend/.env.example`: DATABASE_URL, MANAGEMENT_ORIGIN, EMBED_ORIGIN и HOSTED_DIST с префиксом NODE06_. Не коммитьте этот файл и не копируйте чужие секреты. Соберите фронт, примените онлайн `alembic upgrade head` в окружении сервиса, запустите `node06-service` за HTTPS reverse proxy. Рабочие команды, заголовки безопасности, origin isolation, резервное копирование и проверки описаны ниже; пример не является командой для чужого production-сервера.

An independent instance needs its own database, service configuration and HTTPS origins. Registrations and influence stay local to that instance. Account synchronization and cross-server subscriptions are future work. Configure the static connection values for YOUR service before building. Do not reuse the demo site ID, proof or private environment.

[Backend: установка, окружение и тесты / Backend setup](https://github.com/wratixor/node06/blob/main/backend/README.md)

[Разделение доменов и размещённый фронт / Hosted origin setup](https://github.com/wratixor/node06/blob/main/docs/HOSTED-WIKI-V1.md)

[Порядок деплоя и отката / Deployment checklist](https://github.com/wratixor/node06/blob/main/docs/DEPLOYMENT-HANDOFF.md)

Для Amsterdam используйте существующие скрипты geno-dice-deploy и их локальный конфиг. Автодеплой следит за принятой main, а не любой веткой. После обновления проверьте health, ready, meta и вход/чтение из реального сайта. Наличие успешного билда не доказывает успешный production-деплой.
