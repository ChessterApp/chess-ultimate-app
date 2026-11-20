"""20.11: the first sentence of a spoken answer is read by this server and its sound sent in the chat stream
(src/voice_speak.py) — the page's own request through the site took 1.0-1.8 s to the first sound on production."""

import asyncio
import base64

import pytest

from src import voice_speak, voice_tts


@pytest.mark.unit
class TestTheSentence:
    def test_the_head_is_exactly_the_text_up_to_the_first_end(self):
        text = "На e4 ответь пешкой на e5. Так ты займёшь центр."
        assert voice_speak.first_sentence(text) == "На e4 ответь пешкой на e5."
        assert text.startswith(voice_speak.first_sentence(text))

    def test_a_dot_inside_a_move_is_not_an_end(self):
        assert voice_speak.first_sentence("После 1.e4 e5 2.Nf3 играй Кc6. Дальше развитие.") == "После 1.e4 e5 2.Nf3 играй Кc6."

    def test_no_end_or_nothing_to_say_is_left_to_the_page(self):
        assert voice_speak.first_sentence("Ответь пешкой на e5") is None
        assert voice_speak.first_sentence("[[arrows: e2e4]] .") is None
        assert voice_speak.first_sentence("Очень " * 60 + "длинная фраза.") is None

    def test_what_is_read_has_no_markdown_links_or_records(self):
        assert voice_speak.speakable("**Связка** — см. [урок](https://chesster.io/learn/x).") == "Связка — см. урок."
        assert voice_speak.speakable("[Engine] +0.3 Хороший ход.") == "+0.3 Хороший ход."


class _Resp:
    def __init__(self, chunks):
        self._chunks = chunks

    async def aiter_bytes(self):
        for c in self._chunks:
            yield c

    async def aclose(self):
        pass


@pytest.mark.unit
class TestTheSound:
    def _run(self, monkeypatch, opened):
        async def fake_open(text, locale):
            return opened
        monkeypatch.setattr(voice_tts, "open_speech", fake_open)
        out = []
        ok = asyncio.run(voice_speak.stream("Хороший ход.", "ru", lambda k, p: out.append((k, p))))
        return ok, out

    def test_parts_of_at_least_100_ms_then_done(self, monkeypatch):
        chunks = [b"\x01\x00" * 1000] * 6 + [b"\x02"]  # 2000-byte pieces and an odd byte
        ok, out = self._run(monkeypatch, (voice_tts_kept(), _Resp(chunks), "m", "24000", None))
        audio = [base64.b64decode(p["pcm"]) for k, p in out if k == "speech_audio"]
        assert ok and out[-1] == ("speech_done", {"id": 1, "ok": True})
        assert all(len(a) % 2 == 0 for a in audio) and len(audio[0]) >= voice_speak.MIN_PART_BYTES
        assert sum(len(a) for a in audio) == 12000

    def test_a_refusal_says_not_read_and_the_page_reads_it(self, monkeypatch):
        ok, out = self._run(monkeypatch, (None, None, None, None, object()))
        assert not ok and out == [("speech_done", {"id": 1, "ok": False})]

    def test_another_rate_is_left_to_the_page(self, monkeypatch):
        ok, out = self._run(monkeypatch, (voice_tts_kept(), _Resp([b"\x00" * 9600]), "m", "16000", None))
        assert not ok and out == [("speech_done", {"id": 1, "ok": False})]


def voice_tts_kept():
    from src import voice_http

    return voice_http.KEPT
