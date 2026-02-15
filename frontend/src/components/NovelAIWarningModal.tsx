/**
 * NovelAI Warning Modal Component
 *
 * NovelAIプロバイダー利用時、非Opusプランユーザーに案内を表示するモーダル。
 * tier !== 3 の場合に表示され、続行またはキャンセルを選択できる。
 * tier === 0 (Free/Paper) の場合は未対応プランである旨を追加表示する。
 */

import "./NovelAIWarningModal.css";

interface NovelAIWarningModalProps {
  tier: number;
  onContinue: () => void;
  onCancel: () => void;
}

const TIER_NAMES: Record<number, string> = {
  0: "Free (Paper)",
  1: "Tablet",
  2: "Scroll",
  3: "Opus",
};

export default function NovelAIWarningModal({
  tier,
  onContinue,
  onCancel,
}: NovelAIWarningModalProps) {
  const tierName = TIER_NAMES[tier] ?? `Unknown (${tier})`;
  const isTrialTier = tier === 0;
  const title = isTrialTier
    ? "NovelAI 未対応プランのお知らせ"
    : "NovelAI プランのご案内";

  return (
    <div className="novelai-warning-overlay">
      <div className="novelai-warning-modal">
        <div className="novelai-warning-icon">⚠️</div>
        <h2>{title}</h2>

        <div className="novelai-warning-content">
          <p className="novelai-warning-plan">
            現在のNovelAIプラン: <strong>{tierName}</strong>
          </p>
          {isTrialTier && (
            <p className="novelai-warning-main">
              Paper（無料トライアル）には対応しておりません。
              <br />
              画像・テキスト生成には有料プランが必要です。
            </p>
          )}
          {!isTrialTier && (
            <p className="novelai-warning-detail">
              本アプリは <strong>Opus (tier 3)</strong> を推奨しています。
            </p>
          )}
        </div>

        <div className="novelai-warning-actions">
          {!isTrialTier && (
            <button
              type="button"
              className="novelai-warning-cancel"
              onClick={onCancel}
            >
              キャンセル
            </button>
          )}
          <button
            type="button"
            className="novelai-warning-continue"
            onClick={isTrialTier ? onCancel : onContinue}
          >
            {isTrialTier ? "閉じる" : "続行する"}
          </button>
        </div>

        {!isTrialTier && (
          <p className="novelai-warning-note">
            ※ この警告は「続行する」を選択すると、次回以降表示されません
          </p>
        )}
      </div>
    </div>
  );
}
