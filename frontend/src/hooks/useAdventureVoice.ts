/**
 * Adventure(romance)のセリフ読み上げ hook。
 *
 * AivisSpeech で合成した音声を専用の Audio 要素で再生する。ChatContext の
 * 再生機構は既定ミュートかつチャット専用バーに紐づくため流用しない。
 * 読み上げは補助機能で、失敗しても物語進行を妨げない(alert は出さない)。
 *
 * 読み上げはセグメント(概ね1文)単位のキューで行う。再生中のセグメントの
 * 次の1本だけを先行合成し、最初の声が出るまでの待ちを縮める。ストリーミング
 * 中の追加給餌(appendSegments)に備え、キューは枯渇後も保持して同じ
 * groupKey なら続きとして再開する。currentKey はグループ(手番・トーク返答)
 * 単位で安定させ、セグメントが進んでも変えない(身振り再生のトリガーが
 * 二重発火しないように)。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ensureAivisEngineRunning,
  synthesizeSpeechTimed,
  type VisemeEvent,
} from "../apis/speechSynthesis";
import { clamp01 } from "../utils/bgmPreferences";
import {
  createVisemeCursor,
  type VisemeCursor,
  type VisemeFrame,
  visemeAtTime,
} from "../utils/visemeTimeline";
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

/** 読み上げキューの1セグメント(概ね1文) */
export interface VoiceSegment {
  /** グループ内で一意な識別子。追加給餌の重複防止に使う */
  id: string;
  text: string;
}

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
  /** 現在再生(または合成)中のグループキー。セグメントが進んでも変わらない */
  currentKey: string | null;
  /** enabled かつ TTS 有効かつ話者ありのときだけ true */
  canSpeak: boolean;
  setEnabled: (next: boolean) => void;
  setVolume: (next: number) => void;
  setSpeed: (next: number) => void;
  /** segments を順に合成して連続再生する。前のキューは打ち切る */
  speakSegments: (segments: VoiceSegment[], groupKey: string) => void;
  /**
   * 進行中(または直前)のキューと groupKey が同じなら未知の id だけを
   * 末尾へ追加する。違うグループなら speakSegments と同じ
   */
  appendSegments: (segments: VoiceSegment[], groupKey: string) => void;
  /** 互換: 単一テキストを1セグメントとして読み上げる */
  speak: (text: string, key: string) => Promise<void>;
  stop: () => void;
  /**
   * 再生中の声の音量レベル(0..1)。3D モデルの口パク用で、毎フレーム呼ぶ。
   * 再生していないときや Web Audio が使えないときは 0
   */
  getLevel: () => number;
  /**
   * 再生中の声の viseme 口パクフレーム。毎フレーム呼ぶ。タイムラインは
   * メディア時刻なので再生速度に依存しない。非再生時やタイムラインが
   * 無いときは null(呼び出し側は音量ベースへフォールバックする)
   */
  getMouthFrame: () => VisemeFrame | null;
}

/** 合成済みで再生待ちの音声 */
interface PreparedAudio {
  url: string;
  timeline: VisemeEvent[];
}

interface VoiceQueue {
  /** キューの世代。stop/新グループ開始で requestIdRef が進み無効化される */
  gen: number;
  groupKey: string;
  segments: VoiceSegment[];
  ids: Set<string>;
  prepared: Map<number, PreparedAudio>;
  /** 次に再生する(または再生中の)セグメント index */
  playIndex: number;
  /** 次に合成するセグメント index */
  fetchIndex: number;
  fetching: boolean;
  playingSegment: boolean;
  engineEnsured: boolean;
  /** 合成/再生に失敗した。順序が壊れるため残りと追加給餌は読まない */
  failed: boolean;
  /** 全セグメントを再生し終えた(追加給餌があれば再開する) */
  done: boolean;
}

export function useAdventureVoice(
  options: UseAdventureVoiceOptions,
): UseAdventureVoiceResult {
  const [prefs, setPrefs] = useState<VoicePreferences>(loadVoicePreferences);
  const [status, setStatus] = useState<AdventureVoiceStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [currentKey, setCurrentKey] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  /** 再生中セグメントの blob URL(prepared から取り出したもの) */
  const urlRef = useRef<string | null>(null);
  /** 口パク用の音量メーター。Audio 要素ごとに1回だけ接続する */
  const meterRef = useRef<VoiceLevelMeter | null>(null);
  /** 単調増加の世代 id。古い合成結果や遅延した play() の結果を捨てる */
  const requestIdRef = useRef(0);
  const queueRef = useRef<VoiceQueue | null>(null);
  /** 再生中セグメントの viseme タイムラインと探索カーソル */
  const activeTimelineRef = useRef<VisemeEvent[] | null>(null);
  const visemeCursorRef = useRef<VisemeCursor>(createVisemeCursor());
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
    // ended/error はセグメントごとに engine 側で onended/onerror を張り替える
    audioRef.current = audio;
    if (!meterRef.current) meterRef.current = createVoiceLevelMeter();
    meterRef.current.attach(audio);
    return audio;
  }, []);

  const getLevel = useCallback(() => meterRef.current?.getLevel() ?? 0, []);

  const getMouthFrame = useCallback((): VisemeFrame | null => {
    const timeline = activeTimelineRef.current;
    const audio = audioRef.current;
    if (!timeline || !audio || audio.paused || audio.ended) return null;
    return visemeAtTime(timeline, audio.currentTime, visemeCursorRef.current);
  }, []);

  const engine = useMemo(() => {
    const isCurrent = (gen: number) => requestIdRef.current === gen;

    const clearPrepared = (queue: VoiceQueue) => {
      for (const item of queue.prepared.values()) {
        URL.revokeObjectURL(item.url);
      }
      queue.prepared.clear();
    };

    const resetAudio = () => {
      const audio = audioRef.current;
      if (audio) {
        audio.onended = null;
        audio.onerror = null;
        audio.pause();
        audio.removeAttribute("src");
        audio.load();
      }
      releaseUrl();
      activeTimelineRef.current = null;
    };

    const fail = (gen: number, caught: unknown) => {
      const queue = queueRef.current;
      if (!queue || queue.gen !== gen) return;
      console.warn("Adventure のセリフ読み上げに失敗しました", caught);
      queue.failed = true;
      clearPrepared(queue);
      resetAudio();
      setStatus("error");
      setError(caught instanceof Error ? caught.message : String(caught));
      setCurrentKey(null);
    };

    const tryPlay = (gen: number) => {
      const queue = queueRef.current;
      if (!queue || queue.gen !== gen || queue.failed || queue.playingSegment) {
        return;
      }
      if (queue.playIndex >= queue.segments.length) {
        // キュー枯渇。追加給餌に備えてキュー自体は保持する
        if (!queue.done) {
          queue.done = true;
          setStatus("idle");
          setCurrentKey(null);
        }
        return;
      }
      const prepared = queue.prepared.get(queue.playIndex);
      if (!prepared) return; // 合成待ち。合成完了時に再度呼ばれる
      queue.prepared.delete(queue.playIndex);
      const audio = ensureAudio();
      releaseUrl();
      urlRef.current = prepared.url;
      activeTimelineRef.current =
        prepared.timeline.length > 0 ? prepared.timeline : null;
      visemeCursorRef.current = createVisemeCursor();
      queue.playingSegment = true;
      audio.onended = () => {
        if (!isCurrent(gen)) return;
        const current = queueRef.current;
        if (!current || current.gen !== gen) return;
        releaseUrl();
        activeTimelineRef.current = null;
        current.playingSegment = false;
        current.playIndex += 1;
        void pumpFetch(gen);
        tryPlay(gen);
      };
      audio.onerror = () => {
        if (!isCurrent(gen)) return;
        fail(gen, new Error("playback_failed"));
      };
      audio.src = prepared.url;
      audio.volume = clamp01(volumeRef.current);
      audio.playbackRate = speedRef.current;
      audio
        .play()
        .then(() => {
          if (!isCurrent(gen)) return;
          setStatus("playing");
        })
        .catch((caught) => {
          if (!isCurrent(gen)) return;
          fail(gen, caught);
        });
    };

    const pumpFetch = async (gen: number) => {
      const queue = queueRef.current;
      if (!queue || queue.gen !== gen || queue.failed || queue.fetching) {
        return;
      }
      queue.fetching = true;
      try {
        while (true) {
          const current = queueRef.current;
          if (!current || current.gen !== gen || current.failed) return;
          if (current.fetchIndex >= current.segments.length) return;
          // 先行合成は「再生中の次の1本」まで
          if (current.fetchIndex > current.playIndex + 1) return;
          const index = current.fetchIndex;
          const segment = current.segments[index];
          const { engineDir, useGpu, speakerId } = optionsRef.current;
          if (!speakerId) return;
          if (!current.engineEnsured) {
            await ensureAivisEngineRunning(engineDir, useGpu);
            if (!isCurrent(gen)) return;
            current.engineEnsured = true;
          }
          const timed = await synthesizeSpeechTimed({
            text: segment.text,
            speaker_id: speakerId,
          });
          if (!isCurrent(gen)) return;
          const checked = queueRef.current;
          if (!checked || checked.gen !== gen || checked.failed) return;
          checked.prepared.set(index, {
            url: URL.createObjectURL(timed.blob),
            timeline: timed.timeline,
          });
          checked.fetchIndex = index + 1;
          tryPlay(gen);
        }
      } catch (caught) {
        if (isCurrent(gen)) fail(gen, caught);
      } finally {
        const queueAfter = queueRef.current;
        if (queueAfter && queueAfter.gen === gen) queueAfter.fetching = false;
      }
    };

    const normalizeSegments = (segments: VoiceSegment[]): VoiceSegment[] =>
      segments
        .map((segment) => ({ id: segment.id, text: segment.text.trim() }))
        .filter((segment) => segment.text.length > 0);

    const start = (segments: VoiceSegment[], groupKey: string) => {
      const cleaned = normalizeSegments(segments);
      const { available, speakerId } = optionsRef.current;
      if (
        cleaned.length === 0 ||
        !enabledRef.current ||
        !available ||
        !speakerId
      ) {
        return;
      }
      const gen = requestIdRef.current + 1;
      requestIdRef.current = gen;
      const previous = queueRef.current;
      if (previous) clearPrepared(previous);
      resetAudio();
      queueRef.current = {
        gen,
        groupKey,
        segments: cleaned,
        ids: new Set(cleaned.map((segment) => segment.id)),
        prepared: new Map(),
        playIndex: 0,
        fetchIndex: 0,
        fetching: false,
        playingSegment: false,
        engineEnsured: false,
        failed: false,
        done: false,
      };
      setStatus("loading");
      setError(null);
      setCurrentKey(groupKey);
      void pumpFetch(gen);
    };

    const append = (segments: VoiceSegment[], groupKey: string) => {
      const queue = queueRef.current;
      if (
        !queue ||
        queue.groupKey !== groupKey ||
        queue.gen !== requestIdRef.current
      ) {
        start(segments, groupKey);
        return;
      }
      // 途中で失敗したグループの続きは読まない(先頭が抜けた読み上げになる)
      if (queue.failed) return;
      const fresh = normalizeSegments(segments).filter(
        (segment) => !queue.ids.has(segment.id),
      );
      if (fresh.length === 0) return;
      for (const segment of fresh) queue.ids.add(segment.id);
      queue.segments.push(...fresh);
      if (queue.done) {
        // 枯渇後の再開。currentKey を戻し、再生が始まるまで loading にする
        queue.done = false;
        setStatus("loading");
        setCurrentKey(groupKey);
      }
      void pumpFetch(queue.gen);
      tryPlay(queue.gen);
    };

    const stopAll = () => {
      requestIdRef.current += 1;
      const queue = queueRef.current;
      if (queue) clearPrepared(queue);
      queueRef.current = null;
      resetAudio();
      setStatus("idle");
      setCurrentKey(null);
    };

    return { start, append, stopAll };
  }, [ensureAudio, releaseUrl]);

  const speakSegments = useCallback(
    (segments: VoiceSegment[], groupKey: string) => {
      engine.start(segments, groupKey);
    },
    [engine],
  );

  const appendSegments = useCallback(
    (segments: VoiceSegment[], groupKey: string) => {
      engine.append(segments, groupKey);
    },
    [engine],
  );

  const speak = useCallback(
    async (rawText: string, key: string) => {
      engine.start([{ id: `${key}#0`, text: rawText }], key);
    },
    [engine],
  );

  const stop = useCallback(() => {
    engine.stopAll();
  }, [engine]);

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
      engine.stopAll();
      audioRef.current = null;
      meterRef.current?.dispose();
      meterRef.current = null;
    };
  }, [engine]);

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
    speakSegments,
    appendSegments,
    speak,
    stop,
    getLevel,
    getMouthFrame,
  };
}
