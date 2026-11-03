import { useCallback, useState } from "react";
import { fetchAnlasBalance } from "../apis/anlas";
import { hasApiKeyConsent } from "../components/apiKeyConsentStorage";
import { useSettings } from "../contexts/SettingsContext";
import type { NovelAISubscriptionResponse } from "../types";
import { readStorageFlag, writeStorageFlag } from "../utils/storage";

// 非 Opus の警告で「続行」を選んだら、以後はプランを確かめ直さない
const NOVELAI_OPUS_CONFIRMED_KEY = "novelai_opus_confirmed";

export interface NovelaiAccountCheck {
  /** 画像の生成元が NovelAI と分かった時点で呼ぶ。同意が無ければ同意ダイアログを出して待つ */
  startCheck: () => Promise<void>;
  checking: boolean;
  showConsent: boolean;
  consentDeclined: boolean;
  showWarning: boolean;
  acceptConsent: () => Promise<void>;
  declineConsent: () => void;
  continueWithoutOpus: () => void;
  dismissWarning: () => void;
}

/**
 * NovelAI 利用時の確認(API キー利用の同意 → Anlas 残高とプランの取得、非 Opus の警告)。
 * 結果は SettingsContext の anlasBalance / novelaiTier に入る。
 * ダイアログは NovelaiAccountModals で描く。
 */
export function useNovelaiAccountCheck(): NovelaiAccountCheck {
  const { setAnlasBalance, setNovelaiTier } = useSettings();
  const [checking, setChecking] = useState(false);
  const [showConsent, setShowConsent] = useState(false);
  const [consentDeclined, setConsentDeclined] = useState(false);
  const [showWarning, setShowWarning] = useState(false);

  const checkSubscription = useCallback(async () => {
    fetchAnlasBalance().then((balance) => {
      if (balance) {
        setAnlasBalance(balance);
      }
    });

    if (readStorageFlag("local", NOVELAI_OPUS_CONFIRMED_KEY)) {
      return;
    }

    setChecking(true);
    try {
      const subRes = await fetch("/novelai/subscription");
      if (subRes.ok) {
        const subData: NovelAISubscriptionResponse = await subRes.json();
        setNovelaiTier(subData.tier);

        // tier !== 3 (非Opus) の場合、警告を表示
        if (subData.tier !== 3) {
          setShowWarning(true);
        }
      }
    } catch (e) {
      console.warn("Failed to check NovelAI subscription:", e);
    } finally {
      setChecking(false);
    }
  }, [setAnlasBalance, setNovelaiTier]);

  const startCheck = useCallback(async () => {
    if (!hasApiKeyConsent()) {
      setShowConsent(true);
      return;
    }
    await checkSubscription();
  }, [checkSubscription]);

  const acceptConsent = useCallback(async () => {
    setShowConsent(false);
    await checkSubscription();
  }, [checkSubscription]);

  const declineConsent = useCallback(() => {
    setShowConsent(false);
    setConsentDeclined(true);
  }, []);

  const continueWithoutOpus = useCallback(() => {
    writeStorageFlag("local", NOVELAI_OPUS_CONFIRMED_KEY, true);
    setShowWarning(false);
  }, []);

  // 警告を閉じるだけ(次回起動時に再表示)
  const dismissWarning = useCallback(() => setShowWarning(false), []);

  return {
    startCheck,
    checking,
    showConsent,
    consentDeclined,
    showWarning,
    acceptConsent,
    declineConsent,
    continueWithoutOpus,
    dismissWarning,
  };
}
