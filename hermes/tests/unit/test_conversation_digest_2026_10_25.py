"""2026-10-25: the text turn showed the model the last ten exchanges and nothing before them; a long voice
session (the pipeline) makes «а что ты говорил про тот план?» fifteen turns back ordinary. The older
exchanges now go in as one quoted line each (src/conversation_digest.py), newest kept under a cap."""

from src.conversation_digest import KEEP_MESSAGES, conversation_digest
from src.sessions import SessionMessage


def _chat(n_exchanges: int) -> list:
    out = []
    for i in range(1, n_exchanges + 1):
        out.append(SessionMessage(role="user", content=f"Вопрос номер {i}: что делать с конём?"))
        out.append(SessionMessage(role="assistant", content=f"**Ответ {i}.** Конь идёт на f3.\n\n- потом рокировка\n[[arrows: g1f3 green]]"))
    return out


def test_nothing_before_the_recent_window_means_no_digest():
    assert conversation_digest(_chat(10)) == ""           # 20 messages: all shown in full
    assert conversation_digest([]) == ""


def test_older_exchanges_are_quoted_oldest_first_and_markup_is_dropped():
    msgs = _chat(12)                                      # 24 messages: exchanges 1 and 2 are older
    d = conversation_digest(msgs)
    assert d.startswith("Earlier in this conversation")
    lines = d.split("\n")[1:]
    assert lines == [
        "- student: «Вопрос номер 1: что делать с конём?» — coach: «Ответ 1. Конь идёт на f3. потом рокировка»",
        "- student: «Вопрос номер 2: что делать с конём?» — coach: «Ответ 2. Конь идёт на f3. потом рокировка»",
    ]
    assert "Вопрос номер 3" not in d                      # part of the recent window
    assert "never invent" in d


def test_the_cap_keeps_the_newest_older_exchanges_and_says_how_many_are_hidden():
    msgs = _chat(60)
    d = conversation_digest(msgs, max_chars=600)
    body = d.split("\n")[1:]
    assert len(body) >= 3 and body[-1].startswith("- student: «Вопрос номер 50:")   # exchanges 51–60 are recent
    assert "Вопрос номер 1:" not in d
    assert "earlier exchange(s) not shown" in d.split("\n")[0]
    assert len(d) <= 600 + 300                            # the header is outside the body's budget


def test_long_words_are_cut_at_a_word_with_an_ellipsis():
    long_q = "Расскажи " + "очень " * 60 + "подробно про испанскую партию"
    msgs = [SessionMessage(role="user", content=long_q), SessionMessage(role="assistant", content="Ладно.")] + _chat(10)
    d = conversation_digest(msgs)
    line = d.split("\n")[1]
    assert line.startswith("- student: «Расскажи очень") and "…»" in line
    assert len(line) < 160 + 120


def test_the_window_constant_matches_the_turn():
    assert KEEP_MESSAGES == 20
