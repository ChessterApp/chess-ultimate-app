# Тематическая база тренера

Семь файлов — семь разделов ТЗ: `strategy`, `tactics`, `pawn_structures`,
`typical_positions`, `opening`, `middlegame`, `endgame`. Каждый файл — список тем.
Тренер читает их напрямую (`src/knowledge_base.py`), правка файла подхватывается без
рестарта. Инструменты: `list_topics`, `get_topic`.

Черновик текста написан 23.09.2026 ассистентом; **правит методист заказчика**. Позиции
проверены: все FEN легальны, ходы разыгрываются, `best_move` — легальный ход и
согласуется со Stockfish (см. `scripts/check_kb_topics.py`).

## Формат темы

```yaml
- slug: lucena-position          # латиница, дефисы; уникален
  phase: endgame                 # strategy | tactics | pawn_structure | typical_position | opening | middlegame | endgame
  level: 3                       # 1–4, как уровни курсов
  title_ru: Позиция Лусены
  title_en: Lucena position      # необязательно; title_kk — тоже
  summary_ru: >-                 # 3–6 предложений: суть темы
    ...
  summary_en: ...                # одна строка, необязательно
  key_ideas_ru: [..., ...]       # 3–5 пунктов
  typical_mistakes_ru: [...]     # 2–3 пункта
  lichess_themes: [rookEndgame]  # темы задач Lichess для get_puzzle
  eco_codes: [D35]               # дебюты, где тема типична (необязательно)
  lesson_stems: [лусен, мост]    # основы слов для поиска уроков сайта по названию
  positions:
    - title_ru: Позиция Лусены
      fen: "1K6/1P1k4/8/8/8/8/r7/2R5 w - - 0 1"     # ЛИБО fen, ЛИБО moves
      plan_ru: "1.Rc4! ... — мост построен."
      best_move: Rc4                                 # необязательно; проверяется на легальность
    - title_ru: Карлсбад
      moves: "1. d4 d5 2. c4 e6 ..."                  # SAN от начальной позиции; FEN считается сам
      plan_ru: "..."
  model_games:
    - {white: "Botvinnik", black: "Vidmar", year: 1936, note_ru: "..."}
```

Ошибка в теме (битый FEN, нелегальный ход, неизвестный раздел) пишется в лог, тема или
позиция пропускается — остальное продолжает работать.

## Проверка

```
.venv/bin/python -m pytest tests/unit/test_knowledge_base.py     # структура, легальность
STOCKFISH_PATH=$(which stockfish) .venv/bin/python scripts/check_kb_topics.py   # best_move против движка
```

## Зеркало в Supabase

`migrations/019_kb_topics.sql` создаёт `kb_topics` и `kb_positions`;
`scripts/sync_kb_topics.py` заливает туда YAML (для сайта и мобильного приложения).
Тренеру это не нужно.
