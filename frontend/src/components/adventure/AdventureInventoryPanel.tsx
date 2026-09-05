import type { TFunction } from "i18next";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  type AdventureInventoryItem,
  type AdventureInventoryLogEntry,
  type AdventureItemActionKind,
  canActOnRun,
} from "../../apis/adventure";
import { useAdventure } from "../../contexts/AdventureContext";

const CHARACTER_PREFIX = "character:";

/** 所有者・入手元の表記(player / world / reality / character:<name>)を表示名にする */
export function formatInventoryActor(
  value: string | null | undefined,
  t: TFunction,
): string {
  const text = (value ?? "").trim();
  if (!text || text === "world") return t("adventure.inventoryActor.world");
  if (text === "player") return t("adventure.inventoryActor.self");
  if (text === "reality") return t("adventure.inventoryActor.reality");
  return text.startsWith(CHARACTER_PREFIX)
    ? text.slice(CHARACTER_PREFIX.length)
    : text;
}

function isCharacter(value: string | null | undefined): boolean {
  return (value ?? "").startsWith(CHARACTER_PREFIX);
}

/** 持ち物ログ1件を1文にする。現実改変由来は接頭辞で区別する */
export function formatInventoryLogEntry(
  entry: AdventureInventoryLogEntry,
  t: TFunction,
): string {
  const item = entry.item ?? "";
  let text: string;
  switch (entry.type) {
    case "item_transfer":
      if (entry.to === "player") {
        text = isCharacter(entry.from)
          ? t("adventure.inventoryLogEntry.item_transfer_in", {
              item,
              from: formatInventoryActor(entry.from, t),
            })
          : t("adventure.inventoryLogEntry.item_transfer_found", { item });
      } else {
        text = t("adventure.inventoryLogEntry.item_transfer_out", {
          item,
          to: formatInventoryActor(entry.to, t),
        });
      }
      break;
    case "boundary_violation":
      text = t("adventure.inventoryLogEntry.boundary_violation", {
        npc: entry.npc ?? "",
      });
      break;
    case "item_use":
    case "item_discard":
    case "item_wear":
    case "item_unwear":
    case "item_update":
      text = t(`adventure.inventoryLogEntry.${entry.type}`, { item });
      break;
    default:
      text = item;
  }
  return entry.origin === "reality"
    ? t("adventure.inventoryLogEntry.reality", { text })
    : text;
}

/** メッセージ窓のメタ行向けに、先頭の1件と残りの件数をまとめる */
export function formatInventoryEvents(
  entries: AdventureInventoryLogEntry[],
  t: TFunction,
): string {
  if (entries.length === 0) return "";
  const first = formatInventoryLogEntry(entries[0], t);
  return entries.length > 1
    ? `${first} ${t("adventure.inventoryLogEntry.more", { count: entries.length - 1 })}`
    : first;
}

/**
 * ログ行の React key。同じ内容の行が1手番に複数並ぶことがあるため、
 * 内容から作ったキーに出現順の連番を足して一意にする(添字そのものは使わない)
 */
export function keyedInventoryEntries(
  entries: AdventureInventoryLogEntry[],
): { key: string; entry: AdventureInventoryLogEntry }[] {
  const seen = new Map<string, number>();
  return entries.map((entry) => {
    const base = [
      entry.turn,
      entry.type,
      entry.origin,
      entry.item_id ?? "",
      entry.item ?? "",
      entry.npc ?? "",
      entry.from ?? "",
      entry.to ?? "",
    ].join(":");
    const ordinal = seen.get(base) ?? 0;
    seen.set(base, ordinal + 1);
    return { key: `${base}#${ordinal}`, entry };
  });
}

interface AdventureInventoryPanelProps {
  /** 行動を送信したあとポップオーバーを閉じる */
  onClose: () => void;
  /** 過去フレーム閲覧中は操作を止める */
  viewingPast: boolean;
}

/**
 * HUD の「持ち物」ポップオーバーの中身。所持品ごとに capabilities に応じた
 * 操作(渡す・使う・着る/脱ぐ・捨てる)を出し、item_action の手番として送る。
 * 着脱・破棄はサーバが確定し、渡す・使うは相手の意思と状況を LLM が判定する。
 */
export default function AdventureInventoryPanel({
  onClose,
  viewingPast,
}: AdventureInventoryPanelProps) {
  const { t } = useTranslation();
  const { activeRun, streaming, talking, submitTurn } = useAdventure();
  const [giveTarget, setGiveTarget] = useState("");
  if (!activeRun?.inventory_enabled) return null;
  const inventory = activeRun.inventory ?? { items: [], log: [] };
  const sim = activeRun.preset === "romance" ? (activeRun.sim ?? null) : null;
  const partnerName = sim?.partner_name?.trim() ?? "";
  // 渡す相手: romance は攻略対象固定、それ以外は場面に居る人物から選ぶ
  const targets = partnerName
    ? [partnerName]
    : Array.from(
        new Set(
          (activeRun.visual_state?.main_characters ?? [])
            .map((member) => member.name.trim())
            .filter(Boolean),
        ),
      );
  const target = targets.includes(giveTarget) ? giveTarget : (targets[0] ?? "");
  const latestTurn = activeRun.turns[activeRun.turns.length - 1];
  const recentEvents = latestTurn?.world_events_applied ?? [];
  const canAct =
    !streaming && !talking && !viewingPast && canActOnRun(activeRun);
  const recentLog = inventory.log.slice(-5).reverse();

  const act = (
    item: AdventureInventoryItem,
    action: AdventureItemActionKind,
  ) => {
    if (!canAct) return;
    const params = { name: item.name, target };
    const text =
      action === "give"
        ? target
          ? t("adventure.inventoryActionText.give", params)
          : t("adventure.inventoryActionText.giveNoTarget", params)
        : t(`adventure.inventoryActionText.${action}`, params);
    onClose();
    void submitTurn(text, "item_action", {
      itemAction: {
        item_id: item.id,
        action,
        ...(action === "give" && target ? { target } : {}),
      },
    });
  };

  return (
    <>
      <p className="adventure-hud__note">{t("adventure.inventoryPanelHint")}</p>
      {recentEvents.length > 0 && (
        <>
          <p className="adventure-hud__inventory-log">
            {t("adventure.inventoryRecentChanges")}
          </p>
          <ul className="adventure-hud__inventory-events">
            {keyedInventoryEntries(recentEvents).map(({ key, entry }) => (
              <li key={key}>{formatInventoryLogEntry(entry, t)}</li>
            ))}
          </ul>
        </>
      )}
      {inventory.items.length === 0 ? (
        <p className="adventure-hud__note">{t("adventure.inventoryEmpty")}</p>
      ) : (
        <>
          {targets.length > 1 && (
            <label className="adventure-hud__inventory-target">
              <span>{t("adventure.inventoryGiveTarget")}</span>
              <select
                value={target}
                onChange={(event) => setGiveTarget(event.target.value)}
              >
                {targets.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <ul className="adventure-hud__inventory">
            {inventory.items.map((item) => (
              <li key={item.id}>
                <div className="adventure-hud__inventory-head">
                  <strong>{item.name}</strong>
                  {item.quantity > 1 && (
                    <span className="adventure-hud__inventory-count">
                      {t("adventure.inventoryQuantity", { n: item.quantity })}
                    </span>
                  )}
                  {item.worn && (
                    <em className="adventure-hud__inventory-badge">
                      {t("adventure.inventoryWorn")}
                    </em>
                  )}
                </div>
                <span className="adventure-hud__inventory-meta">
                  {t(`adventure.inventoryCategory.${item.category}`, {
                    defaultValue: item.category,
                  })}
                  {" ・ "}
                  {t("adventure.inventoryObtained", {
                    from: formatInventoryActor(item.obtained_from, t),
                    turn: item.obtained_turn,
                  })}
                </span>
                <div className="adventure-hud__inventory-actions">
                  {item.capabilities.includes("give") && (
                    <button
                      type="button"
                      disabled={!canAct || targets.length === 0}
                      title={
                        targets.length === 0
                          ? t("adventure.inventoryNoTarget")
                          : undefined
                      }
                      onClick={() => act(item, "give")}
                    >
                      {t("adventure.inventoryAction.give")}
                    </button>
                  )}
                  {item.capabilities.includes("use") && (
                    <button
                      type="button"
                      disabled={!canAct}
                      onClick={() => act(item, "use")}
                    >
                      {t("adventure.inventoryAction.use")}
                    </button>
                  )}
                  {item.capabilities.includes("wear") && (
                    <button
                      type="button"
                      disabled={!canAct}
                      onClick={() => act(item, item.worn ? "unwear" : "wear")}
                    >
                      {t(
                        item.worn
                          ? "adventure.inventoryAction.unwear"
                          : "adventure.inventoryAction.wear",
                      )}
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={!canAct}
                    onClick={() => act(item, "discard")}
                  >
                    {t("adventure.inventoryAction.discard")}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
      {recentLog.length > 0 && (
        <>
          <p className="adventure-hud__inventory-log">
            {t("adventure.inventoryLog")}
          </p>
          <ul className="adventure-hud__inventory-events">
            {keyedInventoryEntries(recentLog).map(({ key, entry }) => (
              <li key={key}>{formatInventoryLogEntry(entry, t)}</li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
