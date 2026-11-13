import { type MouseEvent, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useHakoniwa } from "../../contexts/HakoniwaContext";

interface HakoniwaErrorBannerProps {
  /**
   * 置き場所。page は画面の流れの中、dialog はダイアログの本文の先頭、
   * overlay は全画面の重ね表示(ADV・会話・タッチ)の上端に重ねる。
   */
  placement?: "page" | "dialog" | "overlay";
  /** 開いた時点で残っている前の操作のエラーを消す(ダイアログ・重ね表示で使う) */
  clearOnMount?: boolean;
}

/**
 * 箱庭の操作のエラー(HakoniwaContext の error)を出す帯。
 * ダイアログや全画面の重ね表示は画面の帯を覆ってしまうため、それぞれの中にも置く。
 */
export default function HakoniwaErrorBanner({
  placement = "page",
  clearOnMount = false,
}: HakoniwaErrorBannerProps) {
  const { t } = useTranslation();
  const { error, clearError } = useHakoniwa();

  useEffect(() => {
    if (clearOnMount) clearError();
  }, [clearOnMount, clearError]);

  if (!error) return null;
  // 重ね表示はクリックで場面が進むので、帯の中のクリックは外へ伝えない
  const stop = (event: MouseEvent) => event.stopPropagation();
  return (
    <div
      className={`hakoniwa-error hakoniwa-error--${placement}`}
      role="alert"
      onClick={stop}
      onKeyDown={(event) => event.stopPropagation()}
    >
      <span>{error}</span>
      <button
        type="button"
        className="hakoniwa-button hakoniwa-button--ghost"
        onClick={clearError}
      >
        {t("hakoniwa.dismissError")}
      </button>
    </div>
  );
}
