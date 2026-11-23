import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { GallerySession } from "../../types";
import { formatSessionDate, mediaUrl } from "../../utils/adventureFormat";
import type { AdventureSourceSelection } from "./AdventureSessionPickerModal";
import "./AdventureSourceSelectionCard.css";

interface AdventureSourceSelectionCardProps {
  selection: AdventureSourceSelection;
  /**
   * セッション由来の選択のときの一覧用情報(useGallerySessionInfo で取得)。
   * あれば名前をこちらで出し、枚数・開始日を添える。取得前・セッション以外は null
   */
  sessionInfo: GallerySession | null;
  /** 右端に並べる操作ボタン */
  children?: ReactNode;
}

/**
 * 開始素材・主人公として選んでいる姿のカード。作成フォームと選択モーダルの先頭で共用する。
 * 同じキャラクターの別セッションを見分けられるよう、セッションには枚数・開始日を出す。
 */
export default function AdventureSourceSelectionCard({
  selection,
  sessionInfo,
  children,
}: AdventureSourceSelectionCardProps) {
  const { t, i18n } = useTranslation();
  // Prompt Expander 由来はキャラ名を持たないため、出どころのラベルを主見出しにする
  const name =
    selection.origin === "prompt_expander"
      ? t("adventure.sourcePicker.promptExpanderOrigin")
      : ((sessionInfo ? sessionInfo.character_name : selection.characterName) ??
        t("adventure.unnamedCharacter"));
  const state =
    selection.pointLabel ??
    (selection.origin === "character"
      ? t("adventure.sourcePicker.characterOrigin")
      : t("adventure.currentState"));
  const meta = sessionInfo
    ? t("adventure.sourcePicker.sessionMeta", {
        items: sessionInfo.item_count,
        date: formatSessionDate(sessionInfo.first_timestamp, i18n.language),
      })
    : null;
  return (
    <div
      className="adventure-source-summary"
      role="group"
      aria-label={t("adventure.selectedSourceSummary", { name, state })}
    >
      <span className="adventure-source-summary__thumb">
        <img src={mediaUrl(selection.thumbnailUrl)} alt="" />
      </span>
      <span className="adventure-source-summary__text">
        <strong>{name}</strong>
        {meta && <span className="adventure-source-summary__meta">{meta}</span>}
        <span>{state}</span>
      </span>
      {children}
    </div>
  );
}
