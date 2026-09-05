import { useCallback, useEffect, useState } from "react";
import {
  type AivisStatus,
  getAivisStatus,
  startAivisEngine,
  stopAivisEngine,
} from "../apis/speechSynthesis";
import { useSettings } from "../contexts/SettingsContext";

/**
 * 音声合成エンジン(AivisSpeech)の状態ポーリングと起動・停止。
 * 設定画面を開かずとも右パネルから操作できるようにする。TTS 無効なら何もしない。
 */
export function useAivisEngine() {
  const { state: settingsState } = useSettings();
  const [status, setStatus] = useState<AivisStatus | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!settingsState.ttsEnabled) {
      return;
    }

    let cancelled = false;
    const refresh = async () => {
      try {
        const next = await getAivisStatus();
        if (!cancelled) {
          setStatus(next);
        }
      } catch {
        // ポーリングでの失敗は画面に出さず次回に委ねる
      }
    };
    void refresh();
    const intervalId = window.setInterval(() => void refresh(), 5000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [settingsState.ttsEnabled]);

  const ready = status?.engine_http === "ok" || status?.process === "running";

  const toggle = useCallback(async () => {
    setBusy(true);
    try {
      if (ready) {
        await stopAivisEngine();
      } else {
        await startAivisEngine({
          engine_dir: settingsState.ttsEngineDir,
          use_gpu: settingsState.ttsUseGpu,
        });
      }
      setStatus(await getAivisStatus());
    } catch {
      // エラー詳細は設定画面の詳細情報で確認できるため、ここでは簡易表示のみとする
    } finally {
      setBusy(false);
    }
  }, [ready, settingsState.ttsEngineDir, settingsState.ttsUseGpu]);

  return { status, ready, busy, toggle };
}
