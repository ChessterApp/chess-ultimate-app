# Обновление Hermes (ИИ-тренер Chesster) на сервере — версия 29.09 (факты в объяснениях, дебюты, без зависаний)

> Эта инструкция лежит в репозитории: `docs/runbooks/hermes-server-update.md`. Актуальная версия — всегда в `main`; после шага 1 она есть и в клоне `/root/hermes-update/chess-ultimate-app/`.

> **Александр:** отправьте этот файл целиком тому Claude, у которого есть доступ к серверу Hermes
> (тому же, что обновлял его в прошлый раз). Больше ничего писать не нужно. Это повторное
> обновление: всё, что уже сделано в прошлый раз (миграции, база задач, переменные), Claude
> проверит и пропустит, так что займёт 10–15 минут. В конце Claude пришлёт отчёт.

---

## Для Claude: задача

Обнови сервис Hermes на боевом сервере до текущего `main` репозитория
`https://github.com/ChessterApp/chess-ultimate-app` (папка `hermes/`), примени миграции, собери
базу задач, перезапусти и проверь. В конце напиши отчёт по шаблону из последнего раздела.

### Что такое Hermes

- Python-сервис ИИ-тренера (FastAPI, порт `8642`). Процесс pm2 `hermes-chess`, каталог
  `/root/hermes-chess`, запуск `.venv/bin/python -m src.server`,
  `HERMES_HOME=/root/hermes-chess/profiles/chess-coach` (см. `hermes/ecosystem.config.js` в репозитории).
- Каталог на сервере — это **содержимое папки `hermes/`** репозитория: в корне `src/`, `profiles/`,
  `scripts/`, `migrations/`, `content/`, плюс серверные `.env` и `.venv`. `.env` читается из
  `/root/hermes-chess/.env`.
- Сайт на Vercel (chesster.io) проксирует запросы страницы `/coach` в Hermes. Сайт обновляется сам
  при каждом пуше в `main` и уже новый; Hermes на сервере обновляется только этой процедурой. Пока он
  старый, новые части сайта (например, заблаговременный анализ позиции) получают от него 404 и
  работают без него.

### Что изменится после обновления

Новое в версии 29.09 (если сервер уже обновляли 28.09, меняется только это):
- **Объяснения по проверенным фактам.** Вместе с оценкой позиции тренер получает факты: что висит без
  защиты, какие фигуры связаны, что грозит после лучшего хода (например, «после Кxb5 угроза Кxc7+ —
  вилка короля и ладьи») и что грозит соперник. Раньше «почему» он придумывал сам и ошибался.
- **Названия дебютов из справочника ECO**, а не «на глаз» (была «Puy Lopez» и путаница итальянской с
  испанской).
- **Совет той стороне, чей ход**; «что изучать дальше» ведёт к урокам сайта; ответ всегда на языке
  вопроса (был случай ответа по-китайски).
- **Нет общих зависаний:** запросы к Supabase больше не останавливают ответы остальным ученикам.
- **Разбор партии быстрее:** сервер сам ставит партию на доску и находит ключевые моменты, пока модель
  начинает отвечать (~5–8 с на весь разбор).
- **Партии мастеров:** на доску грузится только настоящая партия с ходами, тренер знает, какая именно.
- **Замеры скорости каждого хода** в логах: строка `turn timings {...}` в `pm2 logs hermes-chess`.

- **Скорость.** На 36 типичных вопросах первое слово ответа — в среднем через ~1 с вместо ~16 с,
  весь ответ ~4,5 с вместо ~20 с. Для этого: позиция считается движком сразу, как приходит вопрос
  (и заранее, пока ученик смотрит на доску); DeepSeek отвечает без скрытых «раздумий» у самых быстрых
  поставщиков OpenRouter; стрелки пишутся прямо в ответе, без отдельного шага.
- Модели те же, что утвердил заказчик 23.09: DeepSeek V4.1 Flash на обычные вопросы, Gemini 3.8 Flash
  на разбор партий и как запасная. Всё идёт через OpenRouter.
- «Привет» / «спасибо» — ответ примерно за секунду; на вопрос сначала короткая реакция, потом ответ.
- Примеры для понятий («покажи связку») ставятся на доску из уроков сайта или из проверенной базы
  тем — вместе со стрелками; тренер не выдумывает позиции.
- **Разбор партии** начинается через 6–12 с вместо 33–39 с: Gemini 3.8 больше не «раздумывает» на каждом
  шаге, ключевые моменты партии сразу приходят с лучшим ходом движка. Исправлен поиск ошибок (раньше
  выигранная партия выглядела как сплошные «зевки»).
- **Тренер говорит как тренер:** коротко, без «движок оценивает +0.34», без заголовков и списков. Учебные
  инструменты (темы, задачи, уроки) доступны ему всегда — раньше на части вопросов он жаловался ученику,
  что «не все инструменты доступны».
- **Защита от зависаний:** поиск по базе партий мастеров (42 ГБ) сдаётся через 3 с, анализ позиции — через
  3 с, а если поставщик модели замолчал посреди ответа, ход заканчивается через 30 с (раньше 120 с) с
  пометкой ученику.
- Появляются API досок и сессий, партия с тренером, задачи из базы Lichess, импорт партии по ссылке
  (если их ещё не было после прошлого обновления).
- Новых зависимостей, миграций и обязательных переменных нет. Откат настроек скорости без
  выкладки — в разделе «Откат».

### Правила

- **Секреты не печатать** ни в чат, ни в отчёт. Показывать только имена переменных, значения никогда.
- **Python-зависимости не устанавливать и не обновлять**, особенно `hermes-agent`. Новый код новых
  пакетов не требует.
- В `.env` только **добавлять** переменные из шага 5, существующие строки не менять.
- Где написано **СТОП**, остановись, ничего дальше не делай и напиши человеку, что нужно.
- Все команды выполняются на сервере, где живёт процесс pm2 `hermes-chess`. Если ты не на нём,
  зайди по SSH. Если доступа нет: **СТОП**, нужен доступ к серверу Hermes.
- Переменные оболочки между отдельными вызовами могут не сохраняться. Поэтому всё, что нужно
  позже, записывается в файлы в `/root/hermes-update/`. Каждый блок кода ниже выполняй одним вызовом.

---

## Шаг 0. Осмотреться

```bash
pm2 describe hermes-chess | grep -E 'status|exec cwd|script path|script args|interpreter'
df -h /root
command -v rsync git curl python3
```

- `exec cwd` должен быть `/root/hermes-chess`. Если путь другой, дальше везде подставляй его.
- Свободно на диске нужно не меньше 5 ГБ (база задач около 2 ГБ плюс временные файлы). Если меньше:
  **СТОП**.
- Если pm2 запускает Hermes не через `.venv/bin/python -m src.server` (например, через Docker):
  **СТОП**, опиши, что видишь.

Как код попадает на сервер:

```bash
cd /root/hermes-chess
git rev-parse --is-inside-work-tree 2>/dev/null && git remote -v && git status --short | head -20
```

| Что видишь | Вариант |
|---|---|
| Не git-репозиторий | **A**: код обновляется копированием (шаг 4) |
| Git-репозиторий отдельного проекта Hermes, `git status` чистый | **B**: копирование (шаг 4), потом коммит в этот репозиторий |
| Git-репозиторий, в `git status` есть изменённые отслеживаемые файлы | **СТОП**: на сервере локальные правки, их нельзя затирать без решения человека |

Зафиксируй состояние «до», оно пойдёт в отчёт:

```bash
mkdir -p /root/hermes-update && cd /root/hermes-update
curl -s localhost:8642/health; echo
SID0=$(python3 -c 'import uuid; print(uuid.uuid4())'); echo "$SID0" > sid-before
curl -sN --max-time 60 -X POST localhost:8642/api/coach/chat \
  -H 'Content-Type: application/json' -H 'X-User-Id: deploy-check' \
  -d '{"message":"Привет","locale":"ru","session_id":"'"$SID0"'"}' \
  -o hello-before.sse -w 'Привет ДО обновления: %{time_total} с\n'
```

## Шаг 1. Взять свежий main

```bash
mkdir -p /root/hermes-update && cd /root/hermes-update
rm -rf chess-ultimate-app
git clone --depth 1 --branch main https://github.com/ChessterApp/chess-ultimate-app.git
git -C chess-ultimate-app log -1 --format='%h %s (%cd)'
```

Репозиторий приватный. Если на сервере нет доступа к GitHub, клонируй там, где доступ есть, и
скопируй на сервер папку `hermes/` в `/root/hermes-update/chess-ultimate-app/hermes/`.
Если доступа нет нигде: **СТОП**.

**Проверка, что нужные исправления уже в main:**

```bash
grep -q '_small_talk_stream' chess-ultimate-app/hermes/src/server.py \
  && test -f chess-ultimate-app/hermes/src/board_markup.py \
  && test -f chess-ultimate-app/hermes/src/tools/_sqlite_budget.py \
  && grep -q 'COACH_SPEECH_LAYER' chess-ultimate-app/hermes/src/prompt_builder.py \
  && test -f chess-ultimate-app/hermes/src/position_facts.py \
  && grep -q 'turn timings' chess-ultimate-app/hermes/src/server.py \
  && echo "ускорение в main есть" || echo "НЕТ ускорения"
```

Если «НЕТ ускорения»: **СТОП**. Нужная версия ещё не в main. Напиши Александру, чтобы он попросил
того, кто прислал эту инструкцию, влить ветку `feat/coach-speed-2`. Ничего не обновляй.

## Шаг 2. Резервная копия

```bash
TS=$(date +%Y%m%d-%H%M%S); echo "$TS" > /root/hermes-update/backup-ts
tar -czf /root/hermes-backup-$TS.tgz -C /root/hermes-chess \
  --exclude='./.venv' --exclude='./data' --exclude='./metrics' \
  --exclude='./profiles/*/sessions' --exclude='./profiles/*/logs' .
chmod 600 /root/hermes-backup-$TS.tgz
tar -tzf /root/hermes-backup-$TS.tgz | grep -c 'src/server.py'
```

Последняя команда должна вывести `1`. В архив попадают `.env` и `config.yaml`, поэтому права 600.

## Шаг 3. Ключ OpenRouter

```bash
cd /root/hermes-chess
KEY=$(grep '^OPENROUTER_API_KEY=' .env | tail -1 | cut -d= -f2- | tr -d "\"'")
[ -n "$KEY" ] && echo "ключ есть" || echo "КЛЮЧА НЕТ"
curl -s https://openrouter.ai/api/v1/credits -H "Authorization: Bearer $KEY" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin)["data"]; print("остаток на аккаунте, $:", round(d["total_credits"]-d["total_usage"],2))'
curl -s https://openrouter.ai/api/v1/key -H "Authorization: Bearer $KEY" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin)["data"]; print("лимит ключа:", d.get("limit"), "осталось:", d.get("limit_remaining"), "free tier:", d.get("is_free_tier"))'
unset KEY
```

- Ключа нет или остаток меньше $1: **СТОП**. Без баланса обе модели откажут, и ученики увидят
  «Тренер сейчас недоступен».
- Остаток меньше $10 или `free tier: True`: продолжай, но отметь в отчёте. У новых аккаунтов
  OpenRouter лимит 20 запросов в минуту на модель.

## Шаг 4. Обновить код

Сначала посмотри, что изменится, без записи:

```bash
cd /root/hermes-update
cat > rsync-exclude.txt <<'EOF'
.env
.venv/
data/
metrics/
.git/
__pycache__/
profiles/*/sessions/
profiles/*/logs/
profiles/*/auth.json
profiles/*/auth.lock
profiles/*/*.cache*
profiles/*/models_dev_cache.json
profiles/*/state.db
eval/prompt_opt/cache/
eval/prompt_opt/runs/
EOF
rsync -a -n --itemize-changes --exclude-from=rsync-exclude.txt chess-ultimate-app/hermes/ /root/hermes-chess/ | tee rsync-plan.txt | tail -40
wc -l rsync-plan.txt
diff /root/hermes-chess/profiles/chess-coach/config.yaml chess-ultimate-app/hermes/profiles/chess-coach/config.yaml > config-diff.txt; cat config-diff.txt
```

- В `config.yaml` ожидаемо меняются модели (`default`, `tiers`, новый уровень `fallback`).
  Если в старом файле другой `port` (не 8642): **СТОП**.
- Если в плане есть что-то внутри `.env`, `.venv`, `data/`, `sessions/`: **СТОП**, исключения не
  сработали.

Копирование (`--delete` не используется: лишние старые файлы остаются, они не мешают):

```bash
cd /root/hermes-update && rsync -a --exclude-from=rsync-exclude.txt chess-ultimate-app/hermes/ /root/hermes-chess/
```

**Проверка импорта** до перезапуска. Работающий процесс при этом не трогается:

```bash
cd /root/hermes-chess && HERMES_HOME=/root/hermes-chess/profiles/chess-coach \
  .venv/bin/python -c "import src.server; print('import ok')"
```

Если не `import ok`: верни код из копии (раздел «Откат», пункты 2–3, **без** `pm2 restart`), потом
**СТОП** с текстом ошибки.

**Только вариант B:** закоммить синхронизацию в репозиторий Hermes и отправь её в его основную ветку.
Иначе следующая выкладка из этого репозитория откатит исправления.

```bash
cd /root/hermes-chess && git add -A && git diff --cached --name-only | grep -E '(^|/)\.env$' && echo "СТОП: .env в индексе"
git commit -m "sync hermes/ from chess-ultimate-app main $(git -C /root/hermes-update/chess-ultimate-app rev-parse --short HEAD)"
git push
```

Если `.env` попал в индекс: `git reset`, **СТОП**. Если прав на push нет, продолжай и отметь в отчёте.

## Шаг 5. Переменные окружения

```bash
cd /root/hermes-chess && cp .env /root/hermes-update/env-before-$(cat /root/hermes-update/backup-ts)
chmod 600 /root/hermes-update/env-before-*
for v in HERMES_ADMIN_TOKEN WHOP_WEBHOOK_SECRET SUPABASE_URL SUPABASE_SERVICE_KEY OPENROUTER_API_KEY STOCKFISH_PATH COACH_TWO_STAGE COACH_BESTOFN; do
  grep -q "^$v=" .env && echo "$v: задана" || echo "$v: нет"; done
```

- `HERMES_ADMIN_TOKEN`: если нет, создай. Это токен админской аналитики, в отчёте напиши только,
  что он создан и лежит в `.env`.
  ```bash
  echo "HERMES_ADMIN_TOKEN=$(openssl rand -hex 32)" >> .env
  ```
- `WHOP_WEBHOOK_SECRET`: новый код проверяет подпись вебхука Whop. Без секрета вебхук отвечает 500,
  и события подписок теряются. Если переменной нет, проверь, приходят ли вебхуки Whop в Hermes:
  ```bash
  grep -c 'whop-webhook' ~/.pm2/logs/hermes-chess-*.log 2>/dev/null
  ```
  Если совпадения есть: **СТОП**. Нужен секрет вебхука из панели Whop (раздел Developer → Webhooks),
  его даёт владелец аккаунта Whop. Если совпадений нет (вебхуки идут не сюда), продолжай и отметь в отчёте.
- `COACH_TWO_STAGE`: если задана `0`, быстрая реакция выключена. Не меняй, но отметь в отчёте:
  проверка 3 в этом случае покажет старое время.
- `COACH_BESTOFN`: если задана `1`/`true`, вопросы с позицией на доске идут режимом «лучший из двух»: модель пишет два ответа, судья выбирает один, и он приходит целиком через 3–5 с, без первой фразы, примерно вдвое дороже. Не меняй, но выпиши значение в отчёт (строкой `COACH_BESTOFN=…`).
- `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` / `STOCKFISH_PATH` уже должны быть. Если какой-то нет,
  отметь в отчёте, не придумывай значения.

## Шаг 6. Миграции Supabase

Файлы в `/root/hermes-update/chess-ultimate-app/hermes/migrations/`, применять по порядку:

1. `016_token_usage_turn_cache.sql` — поля учёта расходов;
2. `017_usage_views.sql` — представления для отчётов по расходам;
3. `018_coach_boards.sql` — сохранение досок и сессий тренера;
4. `019_kb_topics.sql` — зеркало базы тем для сайта (необязательно, но безвредно).

Все четыре идемпотентны (`IF NOT EXISTS` / `CREATE OR REPLACE`), повторный запуск ничего не ломает.

- Если на сервере есть `psql` и строка подключения к Postgres этого проекта Supabase:
  ```bash
  for f in 016_token_usage_turn_cache 017_usage_views 018_coach_boards 019_kb_topics; do
    psql "$DB_URL" -v ON_ERROR_STOP=1 -f /root/hermes-update/chess-ultimate-app/hermes/migrations/$f.sql || break; done
  ```
- Если доступа к базе нет, это **не** СТОП. Hermes работает и без миграций, только доски не
  переживают перезапуск сервиса. В отчёте попроси человека вставить эти четыре файла по порядку
  в Supabase → SQL Editor.

## Шаг 7. База задач Lichess

Если `/root/hermes-chess/data/puzzles.db` уже есть и больше 1 ГБ, пропусти шаг.

```bash
cd /root/hermes-update
curl -LO https://database.lichess.org/lichess_db_puzzle.csv.zst
cd /root/hermes-chess
nohup .venv/bin/python scripts/import_puzzles.py /root/hermes-update/lichess_db_puzzle.csv.zst \
  > /root/hermes-update/puzzles.log 2>&1 &
```

Сборка идёт 5–10 минут и работает, пока крутится старый процесс. Жди, пока в
`/root/hermes-update/puzzles.log` не появится итог, потом проверь `ls -lh data/puzzles.db`
(около 1,8–2 ГБ). Скрипту нужен `zstd`: Python-пакет `zstandard` или утилита `zstd`. Если нет
ни того, ни другого, поставь утилиту: `apt-get install -y zstd`. Это системная утилита, правило
про Python-зависимости на неё не распространяется.

Если сборка упала, это не СТОП. Тренер без базы ответит на «дай задачу», что база не установлена.
Отметь в отчёте и продолжай.

## Шаг 8. Перезапуск

```bash
pm2 restart hermes-chess && sleep 10
pm2 logs hermes-chess --lines 80 --nostream
```

Если в логах `Traceback` на старте или процесс в статусе `errored`: сделай «Откат», потом **СТОП**
с текстом ошибки. Отдельный случай: ошибка про `persist_session`. Она значит, что `hermes-agent`
на сервере старее нужного. Откати и напиши об этом: нужна git-версия
`git+https://github.com/NousResearch/hermes-agent@d58b305`. Ставить её без согласия человека нельзя.

## Шаг 9. Проверка

```bash
cd /root/hermes-update
# 1. здоровье
curl -s localhost:8642/health; echo
# 2. API досок (в старой версии 404)
SID=$(curl -s -X POST localhost:8642/api/coach/sessions -H 'X-User-Id: deploy-check' \
  -H 'Content-Type: application/json' -d '{}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
echo "$SID" > sid-after
curl -s -o /dev/null -w 'boards: HTTP %{http_code}\n' localhost:8642/api/coach/sessions/$SID/boards -H 'X-User-Id: deploy-check'
# 3. «Привет»
curl -sN --max-time 60 -X POST localhost:8642/api/coach/chat -H 'Content-Type: application/json' \
  -H 'X-User-Id: deploy-check' -d '{"message":"Привет","locale":"ru","session_id":"'"$SID"'"}' \
  -o hello.sse -w 'Привет ПОСЛЕ обновления: %{time_total} с\n'
# 4. пример из базы тем / урока
curl -sN --max-time 180 -X POST localhost:8642/api/coach/chat -H 'Content-Type: application/json' \
  -H 'X-User-Id: deploy-check' -d '{"message":"Покажи на доске пример связки","locale":"ru","session_id":"'"$SID"'"}' \
  -o pin.sse -w 'пример связки: %{time_total} с\n'
# 5. задача (если собрана база)
curl -sN --max-time 180 -X POST localhost:8642/api/coach/chat -H 'Content-Type: application/json' \
  -H 'X-User-Id: deploy-check' -d '{"message":"Дай задачу на вилку","locale":"ru","session_id":"'"$SID"'"}' \
  -o puzzle.sse -w 'задача: %{time_total} с\n'
# 6. скорость ответа по позиции — как на сайте: позиция посчитана заранее
FEN='r1bqkbnr/pp1ppppp/2n5/2p5/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3'
curl -s -o /dev/null -w 'анализ позиции заранее: HTTP %{http_code}, %{time_total} с\n' -X POST localhost:8642/api/coach/voice/engine-note \
  -H 'Content-Type: application/json' -H 'X-User-Id: deploy-check' -d '{"fen":"'"$FEN"'"}'
curl -sN --max-time 60 -X POST localhost:8642/api/coach/chat -H 'Content-Type: application/json' \
  -H 'X-User-Id: deploy-check' -d '{"message":"Какой здесь лучший ход?","locale":"ru","fen":"'"$FEN"'","session_id":"'"$SID"'"}' \
  -o move.sse -w 'лучший ход, весь ответ: %{time_total} с\n'
# 7. разбор партии (идёт через Gemini 3.8)
PGN='1. e4 e5 2. Nf3 d6 3. d4 Bg4 4. dxe5 Bxf3 5. Qxf3 dxe5 6. Bc4 Nf6 7. Qb3 Qe7 8. Nc3 c6 9. Bg5 b5 10. Nxb5 cxb5 11. Bxb5+ Nbd7 12. O-O-O Rd8 13. Rxd7 Rxd7 14. Rd1 Qe6 15. Bxd7+ Nxd7 16. Qb8+ Nxb8 17. Rd8# 1-0'
python3 -c 'import json,sys; print(json.dumps({"message":"Разбери мою партию, я играл чёрными. Где я ошибся?\n\n"+sys.argv[1],"locale":"ru","session_id":sys.argv[2]}))' "$PGN" "$SID" > review.json
curl -sN --max-time 120 -X POST localhost:8642/api/coach/chat -H 'Content-Type: application/json' \
  -H 'X-User-Id: deploy-check' -d @review.json \
  -o review.sse -w 'разбор партии, весь ответ: %{time_total} с\n'
# 8. факты и название дебюта в строке движка (испанская партия после 3...Nf6 4.O-O)
curl -s -X POST localhost:8642/api/coach/voice/engine-note -H 'Content-Type: application/json' \
  -H 'X-User-Id: deploy-check' -d '{"fen":"r1bqkb1r/pppp1ppp/2n2n2/1B2p3/4P3/5N2/PPPP1PPP/RNBQ1RK1 b kq - 5 4"}' \
  | python3 -c 'import sys,json; n=json.load(sys.stdin).get("note",""); print("Opening:", "ЕСТЬ" if "Opening (ECO book)" in n else "НЕТ", "| Facts:", "ЕСТЬ" if "Facts (verified" in n else "НЕТ"); print(n[:400])'
# 9. замеры скорости ходов в логах
pm2 logs hermes-chess --lines 200 --nostream | grep 'turn timings' | tail -3
```

Разбор ответов (SSE экранирует кириллицу, поэтому читать через Python):

```bash
for f in hello pin puzzle move review; do python3 - $f.sse <<'EOF'
import json, re, sys
keys, text = set(), []
for line in open(sys.argv[1], encoding="utf-8"):
    if line.startswith("data: "):
        d = json.loads(line[6:]); keys |= set(d); text.append(d.get("delta", ""))
body = "".join(text)
engine = "ЕСТЬ" if re.search(r"stockfish|движ[оке]|[+-]\d+[.,]\d", body, re.I) else "нет"
print(f"== {sys.argv[1]}: кадры {sorted(keys)}, служебные [[ в тексте: {'ЕСТЬ' if '[[' in body else 'нет'}, "
      f"движок/цифры оценки в тексте: {engine}, длина {len(body)} знаков")
print(body[:700]); print()
EOF
done
```

| # | Что проверяем | Норма |
|---|---|---|
| 1 | `/health` | `"status":"ok"`, `"stockfish":{"available":true`, `"supabase":{"configured":true` |
| 2 | Доски | `HTTP 200` |
| 3 | «Привет» | меньше 3 с, осмысленное приветствие по-русски |
| 4 | Пример связки | есть кадр `board_actions`, текст объясняет связку и опирается на поставленную позицию |
| 5 | Задача | есть кадр `board_actions` (или честное «база задач не установлена», если шаг 7 пропущен) |
| 6 | Лучший ход | анализ заранее — `HTTP 200`; весь ответ до ~10 с (обычно 2–4); есть кадр `board_actions` со стрелками; служебных `[[` в тексте нет; движок и цифры оценки в тексте — «нет» |
| 7 | Разбор партии | весь ответ до ~20 с (обычно 5–10); есть кадр `board_actions` (партия на доске); текст называет 2–3 конкретные ошибки чёрных с номерами ходов (например, 9...b5 или 15...Nxd7), без «движок оценивает» и цифр |
| 8 | Строка движка | `Opening: ЕСТЬ | Facts: ЕСТЬ`, в тексте «Ruy Lopez» |
| 9 | Замеры в логах | есть строки `turn timings {"turn": …, "answer_first": …, "total": …}` от проверок 3–7 |

Во всех ответах не должно быть кадра `error` и текста «Тренер сейчас недоступен». Если он есть,
смотри `pm2 logs hermes-chess --lines 200 --nostream`: чаще всего это ключ или баланс OpenRouter.

Убери тестовые сессии (404 на второй — не ошибка, старая версия могла её не сохранить):

```bash
cd /root/hermes-update
for s in $(cat sid-after sid-before); do
  curl -s -X DELETE localhost:8642/api/coach/sessions/$s -H 'X-User-Id: deploy-check'; echo; done
```

Если проверки 1–4 не проходят и причину не удаётся убрать без правки кода: «Откат», потом **СТОП**.

## Откат

1. `pm2 stop hermes-chess`
2. `TS=$(cat /root/hermes-update/backup-ts)`
3. `tar -xzf /root/hermes-backup-$TS.tgz -C /root/hermes-chess` (возвращает старый код, `.env` и `config.yaml`;
   новые файлы, добавленные при обновлении, остаются, старый код их не использует)
4. `pm2 restart hermes-chess && sleep 10 && curl -s localhost:8642/health`

Миграции откатывать не нужно: они только добавляют поля и таблицы.

Откатить только модели, без отката кода: добавить в `.env`, например,
`COACH_MODEL_DEFAULT=google/gemini-3.8-flash`, `COACH_MODEL_FAST=google/gemini-3.8-flash`,
`COACH_MODEL_ANALYSIS=google/gemini-3.8-flash`, потом `pm2 restart hermes-chess`.

Откатить настройки скорости, без отката кода (строки в `.env`, потом `pm2 restart hermes-chess`):
- `COACH_REASONING_EFFORT=low` — вернуть DeepSeek его «раздумья» (медленнее в 3–10 раз, иногда
  аккуратнее в сложных оценках);
- `COACH_PROVIDER_SORT=` (пусто) — вернуть выбор поставщика OpenRouter по цене (медленнее);
- `COACH_ENGINE_NOTE=0` — не считать позицию заранее;
- `COACH_ANSWER_STYLE=full` — вернуть длинные ответы (без правила краткости);
- `COACH_GEMINI_REASONING_EFFORT=` (пусто) — вернуть Gemini её обычные «раздумья» в разборах партий;
- `STOCKFISH_MAX_MS=0`, `TWIC_QUERY_TIMEOUT_S=30`, `COACH_STREAM_STALL_S=120` — снять новые ограничения по
  времени (анализ позиции, поиск по базе партий, молчащий поставщик модели);
- `COACH_ENGINE_FACTS=0` — строка движка без фактов (только ходы и оценки);
- `COACH_REVIEW_PRESTEP=0` — разбор партии снова целиком на модели (сервер не ищет моменты заранее).

## Отчёт (пришли человеку в таком виде)

```
Обновление Hermes — <дата, время>
Результат: обновлено / откат / остановлено на шаге N (причина)
Код: main <короткий хеш>, вариант A|B; резервная копия /root/hermes-backup-<TS>.tgz
Репозиторий Hermes (вариант B): закоммичено и отправлено / нет прав на push
OpenRouter: остаток $<…>, free tier <да/нет>
Переменные: HERMES_ADMIN_TOKEN <создан/уже был>, WHOP_WEBHOOK_SECRET <задан/нет — вебхуки Whop сюда <идут/не идут>>
COACH_BESTOFN=<значение или «не задана»>, COACH_TWO_STAGE=<значение или «не задана»>
Миграции 016–019: применены / нужно применить вручную в Supabase SQL Editor
База задач: собрана (<размер>) / не собрана (<почему>)
Проверки:
  1 health — …
  2 доски — HTTP …
  3 «Привет» — ДО <…> с, ПОСЛЕ <…> с
  4 пример связки — <…> с, board_actions <есть/нет>, <одна фраза о тексте>
  5 задача — …
  6 лучший ход — весь ответ <…> с, стрелки <есть/нет>, служебные [[ <нет/есть>, движок/цифры в тексте <нет/есть>
  7 разбор партии — весь ответ <…> с, <одна фраза о тексте>
  8 строка движка — Opening <ЕСТЬ/НЕТ>, Facts <ЕСТЬ/НЕТ>
  9 замеры в логах — <строки есть/нет; answer_first и total из последней>
Что нужно от людей: <список или «ничего»>
```
