/**
 * カスタム画像サイズ警告モーダル
 *
 * NovelAIモードで規定サイズを超える画像をアップロードした際に
 * Anlas消費リスクを警告するモーダル。
 * 009-custom-image-anlas-warning
 */

import "./NovelAIWarningModal.css"; // 既存スタイルを再利用

interface CustomImageSizeWarningModalProps {
  width: number;
  height: number;
  onContinue: () => void;
  onCancel: () => void;
}

export default function CustomImageSizeWarningModal({
  width,
  height,
  onContinue,
  onCancel,
}: CustomImageSizeWarningModalProps) {
  return (
    <div className="novelai-warning-overlay">
      <div className="novelai-warning-modal">
        <div className="novelai-warning-icon">⚠️</div>
        <h2>カスタムサイズ警告</h2>

        <div className="novelai-warning-content">
          <p>
            アップロードされた画像サイズ:{" "}
            <strong>
              {width} x {height} px
            </strong>
          </p>
          <p>
            画像サイズがカスタムサイズになっています。
            Opusプランであっても画像生成の度に、20以上のAnlasが消費されるリスクがありますが本当に進めて良いですか。
          </p>
          <p className="novelai-warning-hint">
            NovelAI
            Opusプランの場合、以下のサイズ以下であればAnlas消費は0になります:
          </p>
          <ul className="novelai-warning-sizes">
            <li>縦長: 832 x 1216 px</li>
            <li>横長: 1216 x 832 px</li>
            <li>正方形: 1024 x 1024 px</li>
          </ul>
        </div>

        <div className="novelai-warning-actions">
          <button
            type="button"
            className="novelai-warning-cancel"
            onClick={onCancel}
          >
            キャンセル
          </button>
          <button
            type="button"
            className="novelai-warning-continue"
            onClick={onContinue}
          >
            続行する
          </button>
        </div>
      </div>
    </div>
  );
}
