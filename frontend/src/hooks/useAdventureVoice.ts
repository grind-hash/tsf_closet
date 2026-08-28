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
  createVoiceLevelMeter,
  type VoiceLevelMeter,
} from "../utils/voiceLevelMeter";
import {
  clampVoiceSpeed,
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
  /** 再生速度の倍率。1.0 が等速 */
  speed: number;
  status: AdventureVoiceStatus;
  error: string | null;
  /** 現在再生(または合成)中の読み上げキー */
  currentKey: string | null;
  /** enabled かつ TTS 有効かつ話者ありのときだけ true */
  canSpeak: boolean;
  setEnabled: (next: boolean) => void;
  setVolume: (next: number) => void;
  setSpeed: (next: number) => void;
  /** text を合成して再生する。前の読み上げは打ち切る。key は再生中表示の識別用 */
  speak: (text: string, key: string) => Promise<void>;
  stop: () => void;
  /**
   * 再生中の声の音量レベル(0..1)。3D モデルの口パク用で、毎フレーム呼ぶ。
   * 再生していないときや Web Audio が使えないときは 0
   */
  getLevel: () => number;
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
  /** 口パク用の音量メーター。Audio 要素ごとに1回だけ接続する */
  const meterRef = useRef<VoiceLevelMeter | null>(null);
  /** 単調増加のリクエスト id。古い合成結果や遅延した play() の結果を捨てる */
  const requestIdRef = useRef(0);
  const enabledRef = useRef(prefs.enabled);
  const volumeRef = useRef(prefs.volume);
  const speedRef = useRef(prefs.speed);
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
    // 速度を変えても声の高さが変わらないようにする(既定で true だが明示する)
    audio.preservesPitch = true;
    audio.playbackRate = speedRef.current;
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
    if (!meterRef.current) meterRef.current = createVoiceLevelMeter();
    meterRef.current.attach(audio);
    return audio;
  }, []);

  const getLevel = useCallback(() => meterRef.current?.getLevel() ?? 0, []);

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
        audio.playbackRate = speedRef.current;
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

  // 再生速度は再生中でも即座に反映する(合成し直さない)
  const setSpeed = useCallback((next: number) => {
    const clamped = clampVoiceSpeed(next);
    speedRef.current = clamped;
    if (audioRef.current) audioRef.current.playbackRate = clamped;
    setPrefs((prev) => {
      const merged = { ...prev, speed: clamped };
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
      meterRef.current?.dispose();
      meterRef.current = null;
    };
  }, [releaseUrl]);

  return {
    enabled: prefs.enabled,
    volume: prefs.volume,
    speed: prefs.speed,
    status,
    error,
    currentKey,
    canSpeak: prefs.enabled && options.available && Boolean(options.speakerId),
    setEnabled,
    setVolume,
    setSpeed,
    speak,
    stop,
    getLevel,
  };
}
