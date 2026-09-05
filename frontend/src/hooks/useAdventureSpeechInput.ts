import { useCallback, useEffect, useRef, useState } from "react";
import {
  loadSpeechInputPreferences,
  saveSpeechInputPreferences,
} from "../utils/speechInputPreferences";
import type { AdventureVoiceStatus } from "./useAdventureVoice";
import { type SpeechInputErrorCode, useSpeechInput } from "./useSpeechInput";

interface UseAdventureSpeechInputOptions {
  /** i18n の言語コード。ja 系なら日本語で認識する */
  language: string;
  /** 入力欄の現在値（聞き取り開始時点の内容を土台にする） */
  input: string;
  setInput: (value: string) => void;
  /** 自動送信 ON で確定したときの送信 */
  onSubmit: (value: string) => void;
  /** トークモードが表示中か。離れたら聞き取りを止める */
  active: boolean;
  voiceStatus: AdventureVoiceStatus;
  /** 聞き取り開始前に読み上げを止める（モデルの声を拾わない） */
  stopVoice: () => void;
}

/**
 * トークモードの音声入力。暫定テキストは入力欄へ流し込み、確定で置き換える。
 * 自動送信は既定 OFF（認識結果を確認してから送る）。
 */
export function useAdventureSpeechInput({
  language,
  input,
  setInput,
  onSubmit,
  active,
  voiceStatus,
  stopVoice,
}: UseAdventureSpeechInputOptions) {
  const [prefs, setPrefs] = useState(loadSpeechInputPreferences);
  const prefsRef = useRef(prefs);
  prefsRef.current = prefs;
  const [error, setError] = useState<SpeechInputErrorCode | null>(null);
  /** 聞き取り開始時点の入力欄の内容。認識結果はこの後ろへ足す */
  const micBaseRef = useRef("");
  const speech = useSpeechInput({
    lang: language.toLowerCase().startsWith("ja") ? "ja-JP" : "en-US",
    onInterim: (text) => setInput(micBaseRef.current + text),
    onFinal: (text) => {
      const merged = `${micBaseRef.current}${text}`;
      setInput(merged);
      if (prefsRef.current.autoSend && merged.trim()) {
        onSubmit(merged);
      }
    },
    onError: (code) => setError(code),
  });
  const toggleAutoSend = useCallback(() => {
    setPrefs((prev) => {
      const merged = { ...prev, autoSend: !prev.autoSend };
      saveSpeechInputPreferences(merged);
      return merged;
    });
  }, []);

  // 読み上げが始まったら聞き取りを止める(モデルの声を拾わない)。
  // トークモードを離れたときも止める
  const listening = speech.listening;
  const stop = speech.stop;
  useEffect(() => {
    if (!listening) return;
    if (!active || voiceStatus === "loading" || voiceStatus === "playing") {
      stop();
    }
  }, [listening, active, voiceStatus, stop]);

  const start = speech.start;
  const startListening = useCallback(() => {
    setError(null);
    // 読み上げ中の声をマイクが拾わないよう先に止める
    stopVoice();
    micBaseRef.current = input;
    start();
  }, [input, start, stopVoice]);

  return {
    supported: speech.supported,
    listening,
    prefs,
    error,
    toggleAutoSend,
    startListening,
    stopListening: stop,
  };
}
