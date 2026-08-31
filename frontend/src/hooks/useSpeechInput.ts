/**
 * トークモードの音声入力(Web Speech API)hook。
 *
 * プッシュトゥトーク方式: start() で聞き取りを始め、発話の終端か無音で
 * ブラウザ側が自動終了する(continuous=false)。認識はブラウザ内蔵機能で、
 * Chrome では音声がベンダーのサーバーへ送られる(UI 側で注記する)。
 * 非対応ブラウザ(Firefox/Safari 等)では supported=false になり、UI は
 * マイクボタンを出さない。
 */
import { useCallback, useEffect, useRef, useState } from "react";

export type SpeechInputErrorCode =
  | "not-allowed"
  | "no-speech"
  | "network"
  | "unknown";

export interface UseSpeechInputOptions {
  /** 認識言語(BCP 47)。例: "ja-JP" / "en-US" */
  lang: string;
  /** 認識途中のテキスト(確定分 + 暫定分) */
  onInterim: (text: string) => void;
  /** 認識の確定テキスト。空文字は届かない */
  onFinal: (text: string) => void;
  onError?: (code: SpeechInputErrorCode) => void;
}

export interface UseSpeechInputResult {
  /** ブラウザが SpeechRecognition を持つか。false なら UI を出さない */
  supported: boolean;
  listening: boolean;
  start: () => void;
  stop: () => void;
}

/** ベンダープレフィックス付きのコンストラクタも拾う */
type SpeechRecognitionLike = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  maxAlternatives: number;
  start: () => void;
  abort: () => void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
};

interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: ArrayLike<{
    isFinal: boolean;
    0: { transcript: string };
  }>;
}

type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  }
}

function resolveCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null;
}

function normalizeError(error: string | undefined): SpeechInputErrorCode {
  switch (error) {
    case "not-allowed":
    case "service-not-allowed":
      return "not-allowed";
    case "no-speech":
      return "no-speech";
    case "network":
      return "network";
    default:
      return "unknown";
  }
}

export function useSpeechInput(
  options: UseSpeechInputOptions,
): UseSpeechInputResult {
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const optionsRef = useRef(options);
  optionsRef.current = options;
  const supported = resolveCtor() !== null;

  const stop = useCallback(() => {
    recognitionRef.current?.abort();
    recognitionRef.current = null;
    setListening(false);
  }, []);

  const start = useCallback(() => {
    if (recognitionRef.current) return; // 二重 start ガード
    const Ctor = resolveCtor();
    if (!Ctor) return;
    let recognition: SpeechRecognitionLike;
    try {
      recognition = new Ctor();
    } catch {
      optionsRef.current.onError?.("unknown");
      return;
    }
    recognition.lang = optionsRef.current.lang;
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event) => {
      if (recognitionRef.current !== recognition) return;
      let finalText = "";
      let interimText = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        const transcript = result[0]?.transcript ?? "";
        if (result.isFinal) finalText += transcript;
        else interimText += transcript;
      }
      if (finalText.trim()) {
        optionsRef.current.onFinal(finalText.trim());
      } else if (interimText) {
        optionsRef.current.onInterim(interimText);
      }
    };
    recognition.onerror = (event) => {
      if (recognitionRef.current !== recognition) return;
      recognitionRef.current = null;
      setListening(false);
      // aborted は stop() 由来なので通知しない
      if (event.error === "aborted") return;
      optionsRef.current.onError?.(normalizeError(event.error));
    };
    recognition.onend = () => {
      if (recognitionRef.current !== recognition) return;
      recognitionRef.current = null;
      setListening(false);
    };
    recognitionRef.current = recognition;
    setListening(true);
    try {
      recognition.start();
    } catch {
      recognitionRef.current = null;
      setListening(false);
      optionsRef.current.onError?.("unknown");
    }
  }, []);

  // アンマウント時は聞き取りを打ち切る
  useEffect(() => {
    return () => {
      recognitionRef.current?.abort();
      recognitionRef.current = null;
    };
  }, []);

  return { supported, listening, start, stop };
}
