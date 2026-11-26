import { useTranslation } from "react-i18next";
import {
  CHARACTER_SORT_ORDERS,
  type CharacterSortOrder,
  isCharacterSortOrder,
} from "../../utils/characterSort";
import "./CharactersScreen.css";

const ORDER_LABEL_KEYS = {
  created_desc: "characters.sort.createdDesc",
  created_asc: "characters.sort.createdAsc",
  name_asc: "characters.sort.nameAsc",
  name_desc: "characters.sort.nameDesc",
} as const satisfies Record<CharacterSortOrder, string>;

interface CharacterSortSelectProps {
  value: CharacterSortOrder;
  onChange: (order: CharacterSortOrder) => void;
  className?: string;
}

/** キャラクター一覧の並び順の選択(一覧画面と選択モーダルのキャラクタータブで共用) */
export default function CharacterSortSelect({
  value,
  onChange,
  className,
}: CharacterSortSelectProps) {
  const { t } = useTranslation();
  return (
    <label className={`character-sort ${className ?? ""}`.trim()}>
      <span className="character-sort__label">
        {t("characters.sort.label")}
      </span>
      <select
        value={value}
        onChange={(event) => {
          if (isCharacterSortOrder(event.target.value)) {
            onChange(event.target.value);
          }
        }}
      >
        {CHARACTER_SORT_ORDERS.map((order) => (
          <option key={order} value={order}>
            {t(ORDER_LABEL_KEYS[order])}
          </option>
        ))}
      </select>
    </label>
  );
}
