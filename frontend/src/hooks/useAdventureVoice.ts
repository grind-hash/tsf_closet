/**
 * Adventure(romance)のセリフ読み上げ hook。
 *
 * AivisSpeech で合成した音声を専用の Audio 要素で再生する。ChatContext の
 * 再生機構は既定ミュートかつチャット専用バーに紐づくため流用しない。
 * 読み上げは補助機能で、失敗しても物語進行を妨げない(alert は出さない)。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ensureAivisEngineRunning,
  synthesizeSpeech,
} from "../apis/speechSynthesis";
import { clamp01 } from "../utils/bgmPreferences";
import {
  loadVoicePreferences,
  saveVoicePreferences,
  type VoicePreferences,
} from "../utils/voicePreferences";

export type AdventureVoiceStatus = "idle" | "loading" | "playing" | "error";

export interface UseAdventureVoiceOptions {
  /** 設定画面の音声合成(TTS)が有効か。OFF なら speak は何もしない */
  available: boolean;
  /** AivisSpeech のスタイルID(無ければ話者ID)。無ければ speak は何もしない */
  speakerId: string | null;
  engineDir: string;
  useGpu: boolean;
}

export interface UseAdventureVoiceResult {
  enabled: boolean;
  volume: number;
  status: AdventureVoiceStatus;
  error: string | null;
  /** 現在再生(または合成)中の読み上げキー */
  currentKey: string | null;
  /** enabled かつ TTS 有効かつ話者ありのときだけ true */
  canSpeak: boolean;
  setEnabled: (next: boolean) => void;
  setVolume: (next: number) => void;
  /** text を合成して再生する。前の読み上げは打ち切る。key は再生中表示の識別用 */
  speak: (text: string, key: string) => Promise<void>;
  stop: () => void;
}

export function useAdventureVoice(
  options: UseAdventureVoiceOptions,
): UseAdventureVoiceResult {
  const [prefs, setPrefs] = useState<VoicePreferences>(loadVoicePreferences);
  const [status, setStatus] = useState<AdventureVoiceStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [currentKey, setCurrentKey] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);
  /** 単調増加のリクエスト id。古い合成結果や遅延した play() の結果を捨てる */
  const requestIdRef = useRef(0);
  const enabledRef = useRef(prefs.enabled);
  const volumeRef = useRef(prefs.volume);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const releaseUrl = useCallback(() => {
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    }
  }, []);

  const ensureAudio = useCallback((): HTMLAudioElement => {
    if (audioRef.current) return audioRef.current;
    const audio = new Audio();
    audio.preload = "auto";
    audio.addEventListener("ended", () => {
      if (audioRef.current !== audio) return;
      setStatus("idle");
      setCurrentKey(null);
    });
    audio.addEventListener("error", () => {
      if (audioRef.current !== audio) return;
      setStatus("error");
      setError("playback_failed");
    });
    audioRef.current = audio;
    return audio;
  }, []);

  const stop = useCallback(() => {
    requestIdRef.current += 1;
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    }
    releaseUrl();
    setStatus("idle");
    setCurrentKey(null);
  }, [releaseUrl]);

  const speak = useCallback(
    async (rawText: string, key: string) => {
      const text = rawText.trim();
      const { available, speakerId, engineDir, useGpu } = optionsRef.current;
      if (!text || !enabledRef.current || !available || !speakerId) return;
      const requestId = requestIdRef.current + 1;
      requestIdRef.current = requestId;
      const audio = ensureAudio();
      audio.pause();
      releaseUrl();
      setStatus("loading");
      setError(null);
      setCurrentKey(key);
      try {
        await ensureAivisEngineRunning(engineDir, useGpu);
        const blob = await synthesizeSpeech({ text, speaker_id: speakerId });
        if (requestId !== requestIdRef.current) return;
        const url = URL.createObjectURL(blob);
        urlRef.current = url;
        audio.src = url;
        audio.volume = clamp01(volumeRef.current);
        await audio.play();
        if (requestId !== requestIdRef.current) return;
        setStatus("playing");
      } catch (caught) {
        if (requestId !== requestIdRef.current) return;
        console.warn("Adventure のセリフ読み上げに失敗しました", caught);
        setStatus("error");
        setError(caught instanceof Error ? caught.message : String(caught));
        setCurrentKey(null);
      }
    },
    [ensureAudio, releaseUrl],
  );

  const setEnabled = useCallback(
    (next: boolean) => {
      enabledRef.current = next;
      setPrefs((prev) => {
        const merged = { ...prev, enabled: next };
        saveVoicePreferences(merged);
        return merged;
      });
      if (!next) stop();
    },
    [stop],
  );

  const setVolume = useCallback((next: number) => {
    const clamped = clamp01(next);
    volumeRef.current = clamped;
    if (audioRef.current) audioRef.current.volume = clamped;
    setPrefs((prev) => {
      const merged = { ...prev, volume: clamped };
      saveVoicePreferences(merged);
      return merged;
    });
  }, []);

  // アンマウント(/adventure 離脱)時は完全に停止する
  useEffect(() => {
    return () => {
      requestIdRef.current += 1;
      const audio = audioRef.current;
      if (audio) {
        audio.pause();
        audio.removeAttribute("src");
        audio.load();
      }
      audioRef.current = null;
      releaseUrl();
    };
  }, [releaseUrl]);

  return {
    enabled: prefs.enabled,
    volume: prefs.volume,
    status,
    error,
    currentKey,
    canSpeak: prefs.enabled && options.available && Boolean(options.speakerId),
    setEnabled,
    setVolume,
    speak,
    stop,
  };
}
