/**
 * 設定画面「Live2D モデル」セクション。
 *
 * 案内役キャラ(セレナ)の Live2D 表示に必要な Live2D Cubism Core は、Live2D
 * Proprietary Software License の配布物のためアプリに同梱していない。ここでは
 * 配置状況を示し、入手先と配置先を案内する。モデル素材自体は同梱されている。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { fetchUserSettings } from "../../apis/settings";
import {
  live2dCoreAvailable,
  resetLive2dCoreAvailable,
} from "../characterChat/live2d/cubismPilotRenderer";
import "./Live2dSettings.css";

/** Cubism SDK for Web の配布ページ */
const SDK_DOWNLOAD_URL = "https://www.live2d.com/sdk/download/web/";
/** Cubism Core の使用許諾契約書 */
const SDK_LICENSE_URL =
  "https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_jp.html";
/** SDK の ZIP から取り出すファイル */
const CORE_FILENAME = "Core/live2dcubismcore.min.js";
/** 配置先。配布パッケージを使う一般の利用者はこちらだけを見ればよい */
const PACKAGED_DIR = "backend/static/live2d/vendor/";
/** ソースを持っている開発者向けの配置先。デバッグモードのときだけ出す */
const DEV_DIR = "frontend/public/live2d/vendor/";

/** 設定画面のセクション見出しに出す要約。判定中は null */
export type Live2dCoreStatus = "ready" | "missing";

interface Live2dSettingsProps {
  onStatusChange?: (status: Live2dCoreStatus | null) => void;
}

export default function Live2dSettings({
  onStatusChange,
}: Live2dSettingsProps) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<Live2dCoreStatus | null>(null);
  const [checking, setChecking] = useState(false);
  // ENABLE_PROMPT_PREVIEW。リポジトリ内のパスは開発者にしか意味がないため、
  // 有効なときだけ添える(配布版の利用者には選べない置き場所で、混乱のもとになる)
  const [showDevPath, setShowDevPath] = useState(false);
  useEffect(() => {
    let cancelled = false;
    void fetchUserSettings()
      .then((settings) => {
        if (!cancelled) setShowDevPath(settings.enable_prompt_preview ?? false);
      })
      .catch(() => {
        // 取得できないときは開発者向けの表示を出さない
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const onStatusChangeRef = useRef(onStatusChange);
  onStatusChangeRef.current = onStatusChange;

  const check = useCallback(async () => {
    setChecking(true);
    try {
      const available = await live2dCoreAvailable();
      const next: Live2dCoreStatus = available ? "ready" : "missing";
      setStatus(next);
      onStatusChangeRef.current?.(next);
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    void check();
  }, [check]);

  const recheck = useCallback(() => {
    resetLive2dCoreAvailable();
    setStatus(null);
    onStatusChangeRef.current?.(null);
    void check();
  }, [check]);

  return (
    <div className="live2d-settings">
      <p className="live2d-settings__description">
        {t("settings.live2d.description")}
      </p>

      <div className="live2d-settings__status">
        <span
          className={`live2d-settings__badge live2d-settings__badge--${
            status === "ready" ? "ready" : "missing"
          }`}
          role="status"
        >
          {status === null
            ? t("settings.live2d.statusChecking")
            : status === "ready"
              ? t("settings.live2d.statusReady")
              : t("settings.live2d.statusMissing")}
        </span>
        <button
          type="button"
          className="live2d-settings__button"
          disabled={checking}
          onClick={recheck}
        >
          {t("settings.live2d.recheck")}
        </button>
      </div>

      <div className="live2d-settings__guide">
        <p className="live2d-settings__guide-title">
          {t("settings.live2d.guideTitle")}
        </p>
        <ol className="live2d-settings__steps">
          <li>
            {t("settings.live2d.step1")}
            <p className="live2d-settings__code">{SDK_DOWNLOAD_URL}</p>
          </li>
          <li>
            {t("settings.live2d.step2")}
            <p className="live2d-settings__code">{CORE_FILENAME}</p>
          </li>
          <li>
            {showDevPath
              ? t("settings.live2d.step3")
              : t("settings.live2d.step3Single")}
            {showDevPath && (
              <p className="live2d-settings__path-label">
                {t("settings.live2d.pathPackaged")}
              </p>
            )}
            <p className="live2d-settings__code">{PACKAGED_DIR}</p>
            {showDevPath && (
              <>
                <p className="live2d-settings__path-label">
                  {t("settings.live2d.pathDev")}
                </p>
                <p className="live2d-settings__code">{DEV_DIR}</p>
              </>
            )}
          </li>
          <li>{t("settings.live2d.step4")}</li>
          <li>{t("settings.live2d.step5")}</li>
        </ol>
        <div className="live2d-settings__actions">
          <button
            type="button"
            className="live2d-settings__button"
            onClick={() =>
              window.open(SDK_DOWNLOAD_URL, "_blank", "noopener,noreferrer")
            }
          >
            {t("settings.live2d.openDownload")}
          </button>
        </div>
      </div>

      <p className="live2d-settings__license">
        {t("settings.live2d.licenseNote")}{" "}
        <a href={SDK_LICENSE_URL} target="_blank" rel="noreferrer">
          {t("settings.live2d.licenseLink")}
        </a>
      </p>
    </div>
  );
}
