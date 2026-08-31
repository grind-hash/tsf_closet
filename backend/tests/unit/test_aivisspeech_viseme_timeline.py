"""Tests for the viseme timeline extraction used by /synthesize-timed.

The timeline is derived from the audio_query mora lengths. Timestamps within a
chunk are scaled to the actual WAV duration, and chunk offsets accumulate the
actual WAV durations so the timeline matches the merged audio.
"""

import wave
from io import BytesIO

import pytest

from gateway.services.aivisspeech_service import (
    AivisSpeechService,
    VisemeEvent,
)


def _mora(
    vowel: str,
    vowel_length: float,
    consonant: str | None = None,
    consonant_length: float | None = None,
) -> dict:
    return {
        "text": "テ",
        "consonant": consonant,
        "consonant_length": consonant_length,
        "vowel": vowel,
        "vowel_length": vowel_length,
        "pitch": 5.0,
    }


def _query(
    accent_phrases: list[dict],
    *,
    speed: float = 1.0,
    pre: float = 0.1,
    post: float = 0.1,
) -> dict:
    return {
        "accent_phrases": accent_phrases,
        "speedScale": speed,
        "prePhonemeLength": pre,
        "postPhonemeLength": post,
    }


def _silent_wav(duration_sec: float, framerate: int = 24000) -> bytes:
    output = BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(framerate)
        writer.writeframes(b"\x00\x00" * int(duration_sec * framerate))
    return output.getvalue()


class TestChunkVisemeEvents:
    def test_maps_vowels_to_visemes_with_consonant_lead_in(self):
        query = _query(
            [
                {
                    "moras": [
                        _mora("a", 0.2),
                        _mora("i", 0.1, consonant="k", consonant_length=0.05),
                    ],
                    "pause_mora": None,
                }
            ]
        )
        events, total = AivisSpeechService._chunk_viseme_events(query)
        assert events == [
            VisemeEvent(t0=0.1, t1=pytest.approx(0.3), viseme="aa", w=1.0),
            # t0 はモーラ開始(子音込み)、t1 は母音終了
            VisemeEvent(
                t0=pytest.approx(0.3), t1=pytest.approx(0.45), viseme="ih", w=1.0
            ),
        ]
        # pre(0.1) + 0.2 + 0.15 + post(0.1)
        assert total == pytest.approx(0.55)

    def test_closed_mouth_phonemes_advance_time_without_events(self):
        query = _query(
            [
                {
                    "moras": [
                        _mora("N", 0.1),
                        _mora("cl", 0.15),
                        _mora("o", 0.2),
                    ],
                    "pause_mora": _mora("pau", 0.3),
                }
            ]
        )
        events, total = AivisSpeechService._chunk_viseme_events(query)
        assert [event.viseme for event in events] == ["oh"]
        # N(0.1) + cl(0.15) の後に o が始まる
        assert events[0].t0 == pytest.approx(0.1 + 0.1 + 0.15)
        # pau も時間だけ進める
        assert total == pytest.approx(0.1 + 0.1 + 0.15 + 0.2 + 0.3 + 0.1)

    def test_devoiced_vowel_uses_reduced_weight(self):
        query = _query([{"moras": [_mora("U", 0.1)], "pause_mora": None}])
        events, _ = AivisSpeechService._chunk_viseme_events(query)
        assert events == [
            VisemeEvent(t0=0.1, t1=pytest.approx(0.2), viseme="ou", w=0.4)
        ]

    def test_speed_scale_shortens_all_times(self):
        query = _query(
            [{"moras": [_mora("e", 0.2)], "pause_mora": None}],
            speed=2.0,
            pre=0.2,
            post=0.2,
        )
        events, total = AivisSpeechService._chunk_viseme_events(query)
        assert events == [
            VisemeEvent(t0=0.1, t1=pytest.approx(0.2), viseme="ee", w=1.0)
        ]
        assert total == pytest.approx(0.3)

    def test_empty_query_yields_no_events(self):
        events, total = AivisSpeechService._chunk_viseme_events(
            _query([], pre=0.0, post=0.0)
        )
        assert events == []
        assert total == 0.0


class TestWavDuration:
    def test_reads_duration_from_wav(self):
        assert AivisSpeechService._wav_duration_sec(_silent_wav(0.5)) == pytest.approx(
            0.5, abs=1e-3
        )


class TestSynthesizeTimed:
    async def test_scales_and_offsets_chunks_to_actual_wav_length(self, monkeypatch):
        service = AivisSpeechService()
        # 予測 0.5 秒 / 実 WAV 1.0 秒 → ratio 2.0。2チャンク目は 1.0 秒の
        # オフセットから始まる
        query = _query(
            [{"moras": [_mora("a", 0.3)], "pause_mora": None}], pre=0.1, post=0.1
        )
        wav = _silent_wav(1.0)

        async def fake_chunks(text: str, speaker: str):
            return [(wav, query), (wav, query)]

        monkeypatch.setattr(service, "_synthesize_chunks", fake_chunks)
        result = await service.synthesize_timed("こんにちは", "1")
        assert result.content_type == "audio/wav"
        assert result.duration_sec == pytest.approx(2.0, abs=1e-3)
        assert [event.viseme for event in result.timeline] == ["aa", "aa"]
        first, second = result.timeline
        assert first.t0 == pytest.approx(0.2, abs=2e-3)
        assert first.t1 == pytest.approx(0.8, abs=2e-3)
        assert second.t0 == pytest.approx(1.2, abs=2e-3)
        assert second.t1 == pytest.approx(1.8, abs=2e-3)
        # 結合済み音声は2チャンク分
        assert AivisSpeechService._wav_duration_sec(result.audio) == pytest.approx(
            2.0, abs=1e-3
        )
