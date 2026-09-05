"""作品シナリオ定義の読み込みと検証。"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)


class ScenarioVisualStyle(BaseModel):
    """作品シナリオ固有の背景ビジュアル固定値。"""

    model_config = ConfigDict(extra="forbid")

    location: dict[str, str]
    surroundings: dict[str, str]
    scene_tags: str = Field(min_length=1, max_length=1800)

    @model_validator(mode="after")
    def validate_localizations(self) -> ScenarioVisualStyle:
        for field_name in ("location", "surroundings"):
            value = getattr(self, field_name)
            if "ja" not in value or "en" not in value:
                raise ValueError(f"visual_style.{field_name} にはjaとenが必要です")
            if (
                not str(value.get("ja") or "").strip()
                or not str(value.get("en") or "").strip()
            ):
                raise ValueError(f"visual_style.{field_name} が空です")
        if not self.scene_tags.strip():
            raise ValueError("visual_style.scene_tags が空です")
        return self


class ScenarioTemplateDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_]+$")
    version: int = Field(default=1, ge=1)
    preset: Literal["infiltration", "escape", "negotiation", "disguise"]
    content_rating: Literal["mature"] = "mature"
    max_turns: int = Field(default=8, ge=1, le=30)
    title: dict[str, str]
    synopsis: dict[str, str]
    setting: dict[str, str]
    objective: dict[str, str]
    constraints: dict[str, list[str]]
    milestones: dict[str, list[dict[str, str]]]
    opening_premise: dict[str, str]
    guidance: str
    visual_style: ScenarioVisualStyle | None = None
    start_state: dict[str, Any]
    rule: dict[str, Any]

    @model_validator(mode="after")
    def validate_localizations(self) -> ScenarioTemplateDefinition:
        localized_fields = (
            self.title,
            self.synopsis,
            self.setting,
            self.objective,
            self.constraints,
            self.milestones,
            self.opening_premise,
        )
        if any("ja" not in value or "en" not in value for value in localized_fields):
            raise ValueError("作品シナリオにはjaとenの定義が必要です")
        if self.rule.get("type") != "equipment_score":
            raise ValueError("未対応の作品シナリオルールです")
        if not isinstance(self.rule.get("items"), list) or not self.rule["items"]:
            raise ValueError("装備採点ルールにはitemsが必要です")
        return self


def _warn_shared_item_aliases(template_id: str, rule: dict[str, Any]) -> None:
    """複数アイテムが同じエイリアスを持つ場合に警告する。

    共有エイリアスは「下着」のように意図的なこともあるが、その入力では該当する
    全アイテムが同時に着脱される。意図的なものは rule.shared_aliases に宣言し、
    宣言のない重複だけを警告する。
    """
    declared = {
        str(alias).strip().lower()
        for alias in rule.get("shared_aliases", [])
        if str(alias).strip()
    }
    owners: dict[str, list[str]] = defaultdict(list)
    for item in rule.get("items", []):
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "")
        for alias in item.get("aliases", []):
            cleaned = str(alias).strip().lower()
            if item_id and cleaned:
                owners[cleaned].append(item_id)
    shared = {
        alias: ids
        for alias, ids in owners.items()
        if len(ids) > 1 and alias not in declared
    }
    if shared:
        logger.warning(
            "Scenario %s shares equipment aliases across items: %s",
            template_id,
            shared,
        )
    unused = sorted(declared - {alias for alias, ids in owners.items() if len(ids) > 1})
    if unused:
        logger.warning(
            "Scenario %s declares shared_aliases that are not shared: %s",
            template_id,
            unused,
        )


def load_scenario_templates() -> dict[str, dict[str, Any]]:
    scenario_dir = Path(__file__).resolve().parents[1] / "scenarios"
    templates: dict[str, dict[str, Any]] = {}
    for path in sorted(scenario_dir.glob("*.json")):
        definition = ScenarioTemplateDefinition.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        if definition.id in templates:
            raise RuntimeError(f"作品シナリオIDが重複しています: {definition.id}")
        _warn_shared_item_aliases(definition.id, definition.rule)
        templates[definition.id] = definition.model_dump()
    return templates


def template_localized(template: dict[str, Any], key: str, language: str) -> Any:
    value = template[key]
    if isinstance(value, dict):
        return value.get(language) or value["en"]
    return value


SCENARIO_TEMPLATES = load_scenario_templates()
