import { useTranslation } from "react-i18next";
import { useAdventure } from "../../contexts/AdventureContext";

interface AdventureGiftShopModalProps {
  isOpen: boolean;
  onClose: () => void;
}

/**
 * romance 専用のギフトショップ。購入と贈呈は1アクション（1スロット消費）で、
 * 贈る品は gift_id としてサーバへ機械可読に渡す。
 */
export default function AdventureGiftShopModal({
  isOpen,
  onClose,
}: AdventureGiftShopModalProps) {
  const { t } = useTranslation();
  const { activeRun, streaming, submitTurn } = useAdventure();

  if (!isOpen) return null;
  const sim = activeRun?.preset === "romance" ? (activeRun.sim ?? null) : null;
  if (!sim) return null;

  const givenGiftIds = new Set(sim.given_gift_ids);

  const handleGive = (giftId: string, giftName: string) => {
    if (streaming || activeRun?.status !== "active") return;
    onClose();
    void submitTurn(
      t("adventure.romance.giftAction", { name: giftName }),
      "gift",
      { giftId },
    );
  };

  return (
    <div
      className="adventure-prompt-modal"
      role="dialog"
      aria-modal="true"
      aria-label={t("adventure.romance.giftShop.title")}
    >
      <button
        type="button"
        className="adventure-prompt-modal__backdrop"
        aria-label={t("adventure.romance.giftShop.close")}
        onClick={onClose}
      />
      <div className="adventure-prompt-modal__panel adventure-gift-shop__panel">
        <h2>{t("adventure.romance.giftShop.title")}</h2>
        <p className="adventure-prompt-modal__hint">
          {t("adventure.romance.giftShop.hint")}
        </p>
        <p className="adventure-gift-shop__money">
          {t("adventure.romance.money")}
          <strong>{sim.money.toLocaleString()}</strong>
        </p>

        <ul className="adventure-gift-shop__list">
          {sim.gift_catalog.map((gift) => {
            const affordable = gift.price <= sim.money;
            const given = givenGiftIds.has(gift.id);
            return (
              <li key={gift.id}>
                <div className="adventure-gift-shop__info">
                  <strong>{gift.name}</strong>
                  <span className="adventure-gift-shop__meta">
                    <em className={`adventure-gift-shop__tier is-${gift.tier}`}>
                      {t(`adventure.romance.giftShop.tiers.${gift.tier}`)}
                    </em>
                    {t("adventure.romance.giftShop.price", {
                      price: gift.price.toLocaleString(),
                    })}
                    {given && (
                      <i className="adventure-gift-shop__given">
                        {t("adventure.romance.giftShop.givenBefore")}
                      </i>
                    )}
                  </span>
                </div>
                <button
                  type="button"
                  className="is-primary"
                  disabled={!affordable || streaming}
                  title={
                    affordable
                      ? undefined
                      : t("adventure.romance.giftShop.insufficientFunds")
                  }
                  onClick={() => handleGive(gift.id, gift.name)}
                >
                  {t("adventure.romance.giftShop.give")}
                </button>
              </li>
            );
          })}
        </ul>

        <div className="adventure-prompt-modal__actions">
          <button type="button" onClick={onClose}>
            {t("adventure.romance.giftShop.close")}
          </button>
        </div>
      </div>
    </div>
  );
}
