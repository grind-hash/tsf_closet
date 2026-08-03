"""作品シナリオ定義の読み込みと検証。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    start_state: dict[str, Any]
    rule: dict[str, Any]

    @model_validator(mode="after")
    def validate_localizations(self) -> "ScenarioTemplateDefinition":
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


def load_scenario_templates() -> dict[str, dict[str, Any]]:
    scenario_dir = Path(__file__).resolve().parents[1] / "scenarios"
    templates: dict[str, dict[str, Any]] = {}
    for path in sorted(scenario_dir.glob("*.json")):
        definition = ScenarioTemplateDefinition.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        if definition.id in templates:
            raise RuntimeError(f"作品シナリオIDが重複しています: {definition.id}")
        templates[definition.id] = definition.model_dump()
    return templates


def template_localized(template: dict[str, Any], key: str, language: str) -> Any:
    value = template[key]
    if isinstance(value, dict):
        return value.get(language) or value["en"]
    return value


SCENARIO_TEMPLATES = load_scenario_templates()
