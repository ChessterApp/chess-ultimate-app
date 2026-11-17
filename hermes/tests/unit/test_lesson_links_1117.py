"""A lesson of the site is a named link in the coach's answer, never a raw address (tester's report 16.11, fixed 17.11).

The answer ended with a bare «chesster.io/learn/chess-basics/…»: the site and the app show ``[text](url)`` as a link
and a bare address as plain text. The server's own lesson line is a markdown link now, and every lesson address left
bare in the outgoing answer is rewritten into one (src/lesson_links.py) — whole or split across the stream's deltas.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.conversation_digest import _brief
from src.lesson_links import LessonLinks, known_lessons, lesson_md, link_lessons
from src.server import app, lesson_link_line, session_store
from src.user_profile import UserProfile

URL = "https://chesster.io/learn/chess-basics/mate-in-one"
LESSON = {"lesson_id": "l1", "title": "Мат в один ход", "url": URL, "course": {"title": "Основы шахмат"}}
SOURCES = [json.dumps(LESSON, ensure_ascii=False)]


@pytest.mark.unit
class TestWholeText:
    @pytest.mark.parametrize("written", [
        "chesster.io/learn/chess-basics/mate-in-one",                 # as the tester saw it: no scheme
        "https://chesster.io/learn/chess-basics/mate-in-one",
        "http://www.chesster.io/learn/chess-basics/mate-in-one",
        "<https://chesster.io/learn/chess-basics/mate-in-one>",
        "`chesster.io/learn/chess-basics/mate-in-one`",
    ])
    def test_a_bare_address_becomes_a_link_named_by_the_lesson(self, written):
        out = link_lessons(f"Пройди урок: {written}. Потом вернёмся.", SOURCES, "ru")
        host = "http://www.chesster.io" if written.startswith("http://www") else "https://chesster.io"
        assert out == f"Пройди урок: [Мат в один ход]({host}/learn/chess-basics/mate-in-one). Потом вернёмся."

    def test_a_schools_host_keeps_its_host_and_gets_the_title_by_the_path(self):
        out = link_lessons("Урок: chess-empire.chesster.io/learn/chess-basics/mate-in-one", SOURCES, "ru")
        assert out == "Урок: [Мат в один ход](https://chess-empire.chesster.io/learn/chess-basics/mate-in-one)"

    @pytest.mark.parametrize("language,lesson,course,programme", [
        ("ru", "урок", "курс", "уроки"), ("en", "lesson", "course", "lessons"),
        ("kz", "сабақ", "курс", "сабақтар"), ("kk", "сабақ", "курс", "сабақтар"),
    ])
    def test_without_a_known_title_a_neutral_word_in_the_answers_language(self, language, lesson, course, programme):
        out = link_lessons("a chesster.io/learn/x/y b chesster.io/learn/x c chesster.io/learn", [], language)
        assert out == (f"a [{lesson}](https://chesster.io/learn/x/y) b [{course}](https://chesster.io/learn/x) "
                       f"c [{programme}](https://chesster.io/learn)")

    @pytest.mark.parametrize("text", [
        f"Пройди [урок «Мат в один ход»]({URL}) и возвращайся.",
        f"**[Мат в один ход]({URL})**",
        f"[урок]({URL} \"подсказка\")",
        "Партия: https://lichess.org/learn/x и chess.com/learn/y",       # not the site's
        "Смотри chesster.io/learning и chesster.io/pricing.",            # not a lesson address
        "Сыграй Nf3. Then chess is fun.",
    ])
    def test_a_markdown_link_and_other_addresses_are_left_alone(self, text):
        assert link_lessons(text, SOURCES, "ru") == text

    def test_a_link_whose_text_is_the_raw_address_gets_the_name(self):
        out = link_lessons(f"[chesster.io/learn/chess-basics/mate-in-one]({URL})", SOURCES, "ru")
        assert out == f"[Мат в один ход]({URL})"

    def test_the_sentences_punctuation_stays_outside_the_link(self):
        out = link_lessons(f"Вот он: {URL}. А этот ({URL}), и «{URL}»?", [], "ru")
        assert out == f"Вот он: [урок]({URL}). А этот ([урок]({URL})), и «[урок]({URL})»?"


@pytest.mark.unit
class TestKnownLessons:
    def test_titles_come_from_every_shape_the_tools_return(self):
        topic = {"site_lessons": [{"title": "Рентген. Пример 2.", "url": "https://chesster.io/learn/t/x-2"}],
                 "example": {"source": "site_lesson", "title": "Рентген. Пример 1.", "url": "https://chesster.io/learn/t/x-1"}}
        puzzle = {"puzzles": [{"puzzle_id": "site:1:1", "lesson": "Ладья — Набор 1", "url": "https://chesster.io/learn/b/rook-1"}]}
        path = {"course": {"title": "Основы шахмат", "url": "https://chesster.io/learn/b"},
                "modules": [{"lessons": [LESSON]}]}
        known = known_lessons([json.dumps(topic, ensure_ascii=False), puzzle, json.dumps(path, ensure_ascii=False), "not json"])
        assert known == {"/learn/t/x-2": "Рентген. Пример 2.", "/learn/t/x-1": "Рентген. Пример 1.",
                         "/learn/b/rook-1": "Ладья — Набор 1", "/learn/b": "Основы шахмат",
                         "/learn/chess-basics/mate-in-one": "Мат в один ход"}

    def test_an_address_two_titles_share_names_neither(self):
        # Lessons without a slug fall back to their course's page: the page is not «lesson A».
        rows = [{"title": "Урок A", "url": "https://chesster.io/learn/b"}, {"title": "Урок B", "url": "https://chesster.io/learn/b"}]
        assert known_lessons([rows]) == {}
        assert link_lessons("chesster.io/learn/b", [rows], "ru") == "[курс](https://chesster.io/learn/b)"

    def test_a_title_with_brackets_cannot_break_the_link(self):
        out = link_lessons("chesster.io/learn/a/b", [{"title": "Мат [в один]\nход", "url": "https://chesster.io/learn/a/b"}], "ru")
        assert out == "[Мат в один ход](https://chesster.io/learn/a/b)"


TEXTS = [
    "Пройди урок: chesster.io/learn/chess-basics/mate-in-one.",
    "Урок https://chess-empire.chesster.io/learn/chess-basics/mate-in-one, потом задачи",
    "Урок chess-empire.chesster.io/learn/chess-basics/mate-in-one, потом задачи",
    f"Уже ссылка: [Мат]({URL}) ок",
    "[chesster.io/learn/x/y](https://chesster.io/learn/x/y)",
    "<https://chesster.io/learn/x/y> и `chesster.io/learn/x` и (chesster.io/learn)",
    "см. chesster.io/learning и lichess.org/learn/x. Сыграй Nf3. Then chess is fun.",
    "**[Урок «Ладья»](https://www.chesster.io/learn/a/b)** и ещё https://chesster.io/learn/a/c",
    "Список [1] и [2]: http://chesster.io/learn/a/b?x=1#top — всё.\n\nУрок на сайте: [«X»](https://chesster.io/learn/a/b) (Курс)",
]


@pytest.mark.unit
class TestStream:
    @pytest.mark.parametrize("text", TEXTS)
    def test_split_anywhere_the_stream_gives_the_whole_texts_result(self, text):
        want = link_lessons(text, SOURCES, "ru")
        for i in range(len(text) + 1):
            for k in range(i, len(text) + 1, 3):
                f = LessonLinks(lambda: SOURCES, "ru")
                assert f.feed(text[:i]) + f.feed(text[i:k]) + f.feed(text[k:]) + f.flush() == want, (i, k)
        f = LessonLinks(lambda: SOURCES, "ru")
        assert "".join(f.feed(ch) for ch in text) + f.flush() == want

    def test_text_that_ends_in_a_space_never_waits(self):
        # The answer check releases whole sentences and sentence starts, each ending in a space: nothing is held.
        f = LessonLinks(lambda: SOURCES, "ru")
        for chunk in ("Хороший вопрос. ", "Сыграй Nf3. ", "Then chess, of course. ", "Ход 1. e4 — лучший.\n\n"):
            assert f.feed(chunk) == chunk and f.held == ""

    def test_the_titles_are_asked_when_the_address_goes_out(self):
        results = []
        f = LessonLinks(lambda: results, "ru")
        assert f.feed("Урок: https://chesster.io/learn/chess-ba") == "Урок: "
        results.append(SOURCES[0])   # the tool finished while the address was being written
        assert f.feed("sics/mate-in-one — пройди.") == f"[Мат в один ход]({URL}) — пройди."


@pytest.mark.unit
class TestServerLine:
    @pytest.mark.parametrize("language,lead", [("ru", "Урок на сайте: "), ("kz", "Сайттағы сабақ: "),
                                               ("kk", "Сайттағы сабақ: "), ("en", "Lesson on the site: ")])
    def test_the_servers_own_line_is_a_markdown_link_in_every_language(self, language, lead):
        line = lesson_link_line(SOURCES, "Объяснение без ссылки.", language)
        assert line == f"{lead}[«Мат в один ход»]({URL}) (Основы шахмат)"
        assert link_lessons(line, SOURCES, language) == line        # the rewrite leaves it as it is
        assert lesson_md("Мат [1]", URL) == f"[«Мат 1»]({URL})"

    def test_what_is_read_aloud_or_summarised_is_the_name_not_the_address(self):
        # The page's reader (frontend voice-pipeline ``speakable``) and the conversation digest strip a markdown link
        # with an http(s) destination to its text: the rewritten form is always that.
        out = link_lessons("Пройди урок chess-empire.chesster.io/learn/chess-basics/mate-in-one сегодня.", SOURCES, "ru")
        assert _brief(out, 200) == "Пройди урок Мат в один ход сегодня."

    def test_the_tools_ask_the_model_for_the_link_form(self):
        from src.tools.knowledge_topics import _site_lesson_hint
        from src.tools.puzzles import queued_puzzle_result

        hint = _site_lesson_hint({"title": "Мат в один ход", "url": URL, "kind": "task", "solution": ["Ra8#"]}, "White")
        assert f"[«Мат в один ход»]({URL})" in hint and "Its address" not in hint
        queued = queued_puzzle_result({"puzzle_id": "site:1:2", "fen": "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1",
                                       "solution": ["Ra8#"], "lesson": "Ладья — Набор 1", "url": URL, "n": 2, "of": 5}, 3)
        assert f"[«Ладья — Набор 1»]({URL})" in queued["how_to_show"] and "address:" not in queued["how_to_show"]


def _turn(user, said, locale="ru"):
    client = TestClient(app)
    headers = {"X-User-Id": user}
    sid = client.post("/api/coach/sessions", headers=headers).json()["id"]
    with patch("src.server._create_agent") as mock_agent, patch("src.server.load_user_profile") as mock_profile:
        mock_profile.return_value = UserProfile(user_id=user)
        agent = MagicMock()

        def _chat(_message, stream_callback=None):
            if stream_callback:
                for part in said:
                    stream_callback(part)
            return "ok"

        agent.chat.side_effect = _chat
        mock_agent.return_value = agent
        resp = client.post("/api/coach/chat", headers=headers,
                           json={"message": "Что мне учить дальше?", "session_id": sid, "locale": locale})
        assert resp.status_code == 200
    frames = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
    stored = [m.content for m in session_store.get(sid, user).messages if m.role == "assistant"][-1]
    return "".join(f.get("delta", "") for f in frames), stored


@pytest.mark.unit
class TestTurn:
    def test_the_streamed_answer_and_the_stored_message_carry_the_link(self):
        text, stored = _turn("links-turn", [
            "Дальше по программе — урок про мат в один ход: chess", "ter.io/learn/chess-ba", "sics/mate-in-one.",
            " Пройди его и возвращайся."])
        link = "[урок](https://chesster.io/learn/chess-basics/mate-in-one)"
        assert f"мат в один ход: {link}. Пройди его" in text
        assert text.count("chesster.io") == 1 and stored == text.strip()

    def test_an_address_at_the_very_end_of_the_answer_goes_out(self):
        text, stored = _turn("links-turn-end", ["Пройди этот урок — https://chesster.io/learn/chess-basics/mate-in-one"])
        assert text.endswith("— [урок](https://chesster.io/learn/chess-basics/mate-in-one)") and stored == text.strip()

    def test_an_answer_without_addresses_is_unchanged(self):
        said = ["Хороший вопрос. ", "Начни с тактики: реши пару задач на связку.", " Потом вернёмся к дебюту."]
        text, _ = _turn("links-turn-plain", said)
        assert text == "".join(said)
