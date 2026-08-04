"""TSF Bloomer 育成モードのサービス層。

7日間 × 4アクションのターン制育成ゲームを管理する。
LLM 呼び出しは narrate=True アクション / 拒否ライン / 夜の総括 / ステージアップ / エンディングのみ。
画像生成は SSE エンドポイント (bloomer_router) 側で呼ぶ。
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import shutil
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..consts.bloomer_consts import (
    ACTIONS_PER_DAY,
    ALL_ACTIONS,
    FALLBACK_ENDING_KEY,
    GROWTH_APTITUDE_FLOOR,
    GROWTH_APTITUDE_RANGE,
    GROWTH_CEILING_SOFTNESS,
    INITIAL_OUTFITS,
    MAX_DAYS,
    MAX_NAME_LENGTH,
    MAX_NARRATION_LENGTH,
    MAX_RUNS_PER_USER,
    MILESTONE_CATALOG,
    MILESTONE_DAYS,
    MOOD_NEUTRAL,
    MOOD_NIGHTLY_DRIFT,
    NSFW_STAGE_MAX,
    NSFW_STAGE_TRUST_THRESHOLDS,
    OUTFIT_CATALOG,
    OUTFIT_FIT_MOOD_HIGH,
    OUTFIT_FIT_MOOD_LOW,
    OUTFIT_FIT_THRESHOLD,
    REFUSAL_BASE,
    REFUSAL_MAX,
    REFUSAL_MIN,
    REFUSAL_MOOD_PENALTY,
    REFUSAL_SCALE,
    REFUSAL_STAMINA_RATIO,
    STAGE_REQUIREMENTS,
    STAGE_UNLOCK_OUTFITS,
    AXIS_KEYS,
    AXIS_MAX,
    AXIS_MIN,
)
from ..databases.base import async_session_factory
from ..databases.models import BloomerEvent, BloomerRun, History
from ..settings.config import settings
from .llm_service import LLMServiceError, llm_service
from .session import session_store
from .bloomer_prompts import (
    build_action_reaction_prompt,
    build_ending_prompt,
    build_image_tags_prompt,
    build_nightly_summary_prompt,
    build_refusal_prompt,
    build_stage_up_prompt,
)

logger = logging.getLogger(__name__)


class BloomerError(RuntimeError):
    """育成処理の利用者向けエラー。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, value))


def _load_json(text: str, fallback: Any) -> Any:
    try:
        return json.loads(text) if text else fallback
    except (json.JSONDecodeError, TypeError):
        return fallback


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


# ---------------------------------------------------------------------------
# エンディング選択ロジック（ルールベース）
# ---------------------------------------------------------------------------


def _determine_ending_key(run: BloomerRun) -> str:
    """育て方に応じたエンディングキーを返す。"""
    trust = run.trust
    stage = run.stage
    nsfw_stage = run.nsfw_stage
    axes: dict[str, int] = _load_json(run.axes_json, {})
    growth: dict[str, int] = _load_json(run.growth_json, {})
    decisions: dict[str, str] = _load_json(run.decisions_json, {})
    flags = set(decisions.values())

    effective = {k: axes.get(k, 0) + growth.get(k, 0) for k in AXIS_KEYS}
    top_axis = max(effective, key=lambda k: effective[k], default="composure")

    if trust >= 75 and stage >= 4:
        if "freed" in flags:
            return "blooming_free"
        if "descended" in flags or nsfw_stage >= 3:
            return "devoted_descent"
        return "quiet_bloom"

    if trust >= 50 and stage >= 3:
        if "driven" in flags and top_axis in ("technique", "endurance"):
            return "self_made"
        return "gentle_bloom"

    if trust >= 25 and stage >= 2:
        if "sheltered" in flags:
            return "sheltered_bud"
        return "halfway_there"

    if trust < 15 or stage == 0:
        return "unresponsive_end"

    return FALLBACK_ENDING_KEY


# ---------------------------------------------------------------------------
# 成長適性ファクター (0.5〜1.5)
# ---------------------------------------------------------------------------


def _growth_factor(aptitude: int, current: int) -> float:
    """素質と現在値から成長倍率を返す。上限に近づくほど逓減。"""
    apt_factor = GROWTH_APTITUDE_FLOOR + GROWTH_APTITUDE_RANGE * aptitude / 100.0
    ceiling_factor = 1.0 - GROWTH_CEILING_SOFTNESS * current / 100.0
    return max(0.1, apt_factor * ceiling_factor)


# ---------------------------------------------------------------------------
# BloomerService
# ---------------------------------------------------------------------------


class BloomerService:
    """TSF Bloomer 育成セッションを管理するサービス。"""

    def __init__(self) -> None:
        self._images_dir = settings.history_images_dir.parent / "bloomer_images"
        self._images_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create_run(
        self,
        *,
        user_id: str,
        origin: str,
        name: str,
        source_session_id: str | None = None,
        character_id: str | None = None,
    ) -> BloomerRun:
        name = name.strip()[:MAX_NAME_LENGTH]
        if not name:
            raise BloomerError("invalid_name", "名前が空です")
        if origin not in ("session", "preset"):
            raise BloomerError(
                "invalid_origin", "origin は session か preset のみ有効です"
            )
        if origin == "session" and not source_session_id:
            raise BloomerError(
                "invalid_origin", "session origin には source_session_id が必要です"
            )

        async with async_session_factory() as db:
            # ラン数上限チェック
            count_result = await db.execute(
                select(BloomerRun).where(
                    BloomerRun.user_id == user_id,
                    BloomerRun.status == "active",
                )
            )
            if len(count_result.scalars().all()) >= MAX_RUNS_PER_USER:
                raise BloomerError(
                    "too_many_runs",
                    f"アクティブなランが上限({MAX_RUNS_PER_USER})に達しています",
                )

            # 初期軸素質を算出
            axes = await self._compute_initial_axes(
                user_id=user_id,
                source_session_id=source_session_id,
                character_id=character_id,
            )

            # 初期画像パスを解決
            initial_image_path = await self._resolve_initial_image(
                user_id=user_id,
                source_session_id=source_session_id,
                character_id=character_id,
            )

            run = BloomerRun(
                id=str(uuid.uuid4()),
                user_id=user_id,
                origin=origin,
                source_session_id=source_session_id,
                character_id=character_id,
                name=name,
                day=1,
                max_days=MAX_DAYS,
                actions_left=ACTIONS_PER_DAY,
                stage=0,
                nsfw_stage=0,
                mood=60,
                stamina=100,
                trust=10,
                axes_json=_dump_json(axes),
                growth_json=_dump_json({k: 0 for k in AXIS_KEYS}),
                wardrobe_json=_dump_json(list(INITIAL_OUTFITS)),
                equipped_outfit=INITIAL_OUTFITS[0],
                decisions_json=_dump_json({}),
                status="active",
                initial_image_path=initial_image_path,
                current_image_path=initial_image_path,
            )
            db.add(run)
            await db.commit()
            await db.refresh(run)
            return run

    async def get_run(self, run_id: str, user_id: str) -> BloomerRun:
        async with async_session_factory() as db:
            result = await db.execute(
                select(BloomerRun)
                .where(BloomerRun.id == run_id, BloomerRun.user_id == user_id)
                .options(selectinload(BloomerRun.events))
            )
            run = result.scalar_one_or_none()
            if run is None:
                raise BloomerError("not_found", "育成ランが見つかりません")
            return run

    async def list_runs(self, user_id: str) -> list[BloomerRun]:
        async with async_session_factory() as db:
            result = await db.execute(
                select(BloomerRun)
                .where(BloomerRun.user_id == user_id)
                .order_by(BloomerRun.updated_at.desc())
            )
            return list(result.scalars().all())

    async def delete_run(self, run_id: str, user_id: str) -> None:
        async with async_session_factory() as db:
            result = await db.execute(
                select(BloomerRun).where(
                    BloomerRun.id == run_id, BloomerRun.user_id == user_id
                )
            )
            run = result.scalar_one_or_none()
            if run is None:
                raise BloomerError("not_found", "育成ランが見つかりません")
            await db.delete(run)
            await db.commit()
        # 画像ディレクトリも削除
        run_dir = self._images_dir / run_id
        if run_dir.is_dir():
            shutil.rmtree(run_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # アクション実行
    # ------------------------------------------------------------------

    async def perform_action(
        self,
        run_id: str,
        user_id: str,
        action_key: str,
        language: str = "ja",
        user_text: str | None = None,
    ) -> dict[str, Any]:
        """
        Returns:
          {
            "refused": bool,
            "narration": str | None,
            "run": BloomerRun,
            "event_id": str,
          }
        """
        action_def = ALL_ACTIONS.get(action_key)
        if action_def is None:
            raise BloomerError("invalid_action", f"未知のアクションです: {action_key}")

        async with async_session_factory() as db:
            result = await db.execute(
                select(BloomerRun)
                .where(BloomerRun.id == run_id, BloomerRun.user_id == user_id)
                .options(selectinload(BloomerRun.events))
            )
            run = result.scalar_one_or_none()
            if run is None:
                raise BloomerError("not_found", "育成ランが見つかりません")
            if run.status != "active":
                raise BloomerError("run_ended", "このランはすでに終了しています")
            if run.actions_left <= 0:
                raise BloomerError("no_actions", "本日のアクションを使い切りました")

            # 前提条件チェック
            self._check_action_requirements(run, action_key, action_def)

            # 1日1回制限
            if action_def.get("once_per_day"):
                used_today = any(
                    e.day == run.day and e.action_key == action_key for e in run.events
                )
                if used_today:
                    raise BloomerError(
                        "once_per_day", f"{action_key} は本日すでに実行済みです"
                    )

            # 拒否判定
            refused = self._roll_refusal(run, action_def)
            narration: str | None = None
            event_kind = "refusal" if refused else "action"

            stat_before = {"mood": run.mood, "stamina": run.stamina, "trust": run.trust}

            if refused:
                run.mood = _clamp(run.mood - REFUSAL_MOOD_PENALTY)
                run.actions_left -= 1
                if action_def.get("narrate"):
                    narration = await self._safe_narrate(
                        *build_refusal_prompt(run, action_key, language)
                    )
            else:
                self._apply_effects(run, action_def)
                run.actions_left -= 1
                if action_def.get("narrate"):
                    narration = await self._safe_narrate(
                        *build_action_reaction_prompt(
                            run, action_key, language, user_text
                        )
                    )

            payload = {
                "refused": refused,
                "mood_delta": action_def.get("mood", 0)
                if not refused
                else -REFUSAL_MOOD_PENALTY,
                "stamina_delta": action_def.get("stamina", 0) if not refused else 0,
                "trust_delta": action_def.get("trust", 0) if not refused else 0,
                "axes": action_def.get("axes", {}) if not refused else {},
                "stat_before": stat_before,
                "stat_after": {
                    "mood": run.mood,
                    "stamina": run.stamina,
                    "trust": run.trust,
                },
            }
            event = BloomerEvent(
                id=str(uuid.uuid4()),
                run_id=run.id,
                day=run.day,
                kind=event_kind,
                action_key=action_key,
                payload_json=_dump_json(payload),
                narration=narration,
            )
            db.add(event)
            await db.commit()
            await db.refresh(run)
            stat_after = {
                "mood": run.mood,
                "stamina": run.stamina,
                "trust": run.trust,
            }
            return {
                "refused": refused,
                "narration": narration,
                "run": run,
                "event_id": event.id,
                "stat_before": stat_before,
                "stat_after": stat_after,
            }

    def _check_action_requirements(
        self, run: BloomerRun, action_key: str, action_def: dict[str, Any]
    ) -> None:
        if run.mood < action_def.get("req_mood", 0):
            raise BloomerError(
                "mood_too_low",
                f"{action_key} には機嫌 {action_def['req_mood']} 以上が必要です",
            )
        if run.trust < action_def.get("req_trust", 0):
            raise BloomerError(
                "trust_too_low",
                f"{action_key} には信頼 {action_def['req_trust']} 以上が必要です",
            )
        if run.nsfw_stage < action_def.get("req_nsfw_stage", 0):
            raise BloomerError(
                "nsfw_locked",
                f"{action_key} は NSFW 段階 {action_def['req_nsfw_stage']} 以上で解禁されます",
            )

    def _roll_refusal(self, run: BloomerRun, action_def: dict[str, Any]) -> bool:
        req_mood = action_def.get("req_mood", 0)
        mood_gap = req_mood - run.mood
        base_chance = REFUSAL_BASE + REFUSAL_SCALE * mood_gap
        # スタミナ半分以下でさらに上昇
        if run.stamina < 50:
            base_chance += REFUSAL_SCALE * (50 - run.stamina) * REFUSAL_STAMINA_RATIO
        chance = max(REFUSAL_MIN, min(REFUSAL_MAX, base_chance))
        return random.random() < chance

    def _apply_effects(self, run: BloomerRun, action_def: dict[str, Any]) -> None:
        run.stamina = _clamp(run.stamina + action_def.get("stamina", 0))
        run.mood = _clamp(run.mood + action_def.get("mood", 0))
        run.trust = _clamp(run.trust + action_def.get("trust", 0))

        axes: dict[str, int] = _load_json(run.axes_json, {k: 50 for k in AXIS_KEYS})
        growth: dict[str, int] = _load_json(run.growth_json, {k: 0 for k in AXIS_KEYS})

        for axis, raw_gain in (action_def.get("axes") or {}).items():
            if axis not in AXIS_KEYS:
                continue
            current = axes.get(axis, 50) + growth.get(axis, 0)
            factor = _growth_factor(axes.get(axis, 50), current)
            actual = max(0, int(round(raw_gain * factor))) if raw_gain > 0 else raw_gain
            growth[axis] = _clamp(
                growth.get(axis, 0) + actual,
                AXIS_MIN - axes.get(axis, 0),
                AXIS_MAX - axes.get(axis, 0),
            )

        run.growth_json = _dump_json(growth)

    # ------------------------------------------------------------------
    # 日進め
    # ------------------------------------------------------------------

    async def advance_day(
        self, run_id: str, user_id: str, language: str = "ja"
    ) -> dict[str, Any]:
        """
        Returns:
          {
            "nightly_narration": str | None,
            "stage_up": int | None,
            "stage_narration": str | None,
            "ended": bool,
            "ending_key": str | None,
            "ending_narration": str | None,
            "run": BloomerRun,
            "milestone_pending": bool,
          }
        """
        async with async_session_factory() as db:
            result = await db.execute(
                select(BloomerRun)
                .where(BloomerRun.id == run_id, BloomerRun.user_id == user_id)
                .options(selectinload(BloomerRun.events))
            )
            run = result.scalar_one_or_none()
            if run is None:
                raise BloomerError("not_found", "育成ランが見つかりません")
            if run.status != "active":
                raise BloomerError("run_ended", "このランはすでに終了しています")

            # 今日のイベントをサマリ用に収集
            events_today = [
                {"kind": e.kind, "action_key": e.action_key}
                for e in run.events
                if e.day == run.day
            ]

            # 夜の総括
            nightly_narration: str | None = None
            nightly_narration = await self._safe_narrate(
                *build_nightly_summary_prompt(run, events_today, language)
            )
            nightly_event = BloomerEvent(
                id=str(uuid.uuid4()),
                run_id=run.id,
                day=run.day,
                kind="milestone",
                action_key="nightly_summary",
                payload_json=_dump_json({}),
                narration=nightly_narration,
            )
            db.add(nightly_event)

            # 機嫌ドリフト
            if run.mood < MOOD_NEUTRAL:
                run.mood = _clamp(run.mood + MOOD_NIGHTLY_DRIFT)
            elif run.mood > MOOD_NEUTRAL:
                run.mood = _clamp(run.mood - MOOD_NIGHTLY_DRIFT)

            # スタミナ回復 (翌日リセット)
            run.stamina = 100
            run.actions_left = ACTIONS_PER_DAY

            # ステージアップ確認
            new_stage = self._check_stage_up(run)
            stage_narration: str | None = None
            if new_stage is not None:
                run.stage = new_stage
                self._unlock_outfits(run, new_stage)
                self._update_nsfw_stage(run)
                stage_narration = await self._safe_narrate(
                    *build_stage_up_prompt(run, new_stage, language)
                )
                stage_event = BloomerEvent(
                    id=str(uuid.uuid4()),
                    run_id=run.id,
                    day=run.day,
                    kind="stage_up",
                    action_key=None,
                    payload_json=_dump_json({"new_stage": new_stage}),
                    narration=stage_narration,
                )
                db.add(stage_event)

            # 日を進める
            run.day += 1

            # 節目チェック (次の日が節目かどうか)
            milestone_pending = run.day in MILESTONE_DAYS

            # 最終日超過 → エンディング
            ended = False
            ending_key: str | None = None
            ending_narration: str | None = None
            if run.day > run.max_days:
                ending_key = _determine_ending_key(run)
                run.ending_key = ending_key
                run.status = "ended"
                ended = True
                ending_narration = await self._safe_narrate(
                    *build_ending_prompt(run, ending_key, language)
                )
                ending_event = BloomerEvent(
                    id=str(uuid.uuid4()),
                    run_id=run.id,
                    day=run.day - 1,
                    kind="ending",
                    action_key=ending_key,
                    payload_json=_dump_json({}),
                    narration=ending_narration,
                )
                db.add(ending_event)

            await db.commit()
            await db.refresh(run)
            return {
                "nightly_narration": nightly_narration,
                "stage_up": new_stage,
                "stage_narration": stage_narration,
                "ended": ended,
                "ending_key": ending_key,
                "ending_narration": ending_narration,
                "run": run,
                "milestone_pending": milestone_pending,
            }

    def _check_stage_up(self, run: BloomerRun) -> int | None:
        """現在のステージより上位の段階条件を満たしていれば新ステージを返す。"""
        axes: dict[str, int] = _load_json(run.axes_json, {})
        growth: dict[str, int] = _load_json(run.growth_json, {})
        axis_total = sum(axes.get(k, 0) + growth.get(k, 0) for k in AXIS_KEYS)

        best_stage: int | None = None
        for req in STAGE_REQUIREMENTS:
            target_stage = req["stage"]
            if target_stage <= run.stage:
                continue
            if (
                run.trust >= req["trust"]
                and axis_total >= req["axis_total"]
                and run.day >= req["day"]
            ):
                best_stage = target_stage
        return best_stage

    def _unlock_outfits(self, run: BloomerRun, stage: int) -> None:
        wardrobe: list[str] = _load_json(run.wardrobe_json, [])
        new_outfits = STAGE_UNLOCK_OUTFITS.get(stage, ())
        for outfit in new_outfits:
            if outfit not in wardrobe:
                wardrobe.append(outfit)
        run.wardrobe_json = _dump_json(wardrobe)

    def _update_nsfw_stage(self, run: BloomerRun) -> None:
        new_nsfw = 0
        for threshold in NSFW_STAGE_TRUST_THRESHOLDS:
            if run.trust >= threshold:
                new_nsfw += 1
        run.nsfw_stage = min(new_nsfw, NSFW_STAGE_MAX)

    # ------------------------------------------------------------------
    # 節目イベント
    # ------------------------------------------------------------------

    async def resolve_milestone(
        self,
        run_id: str,
        user_id: str,
        choice_key: str,
        language: str = "ja",
    ) -> dict[str, Any]:
        async with async_session_factory() as db:
            result = await db.execute(
                select(BloomerRun).where(
                    BloomerRun.id == run_id, BloomerRun.user_id == user_id
                )
            )
            run = result.scalar_one_or_none()
            if run is None:
                raise BloomerError("not_found", "育成ランが見つかりません")
            if run.status != "active":
                raise BloomerError("run_ended", "このランはすでに終了しています")

            milestone = MILESTONE_CATALOG.get(run.day)
            if milestone is None:
                raise BloomerError("no_milestone", f"Day {run.day} に節目はありません")
            choices = milestone.get("choices", {})
            choice = choices.get(choice_key)
            if choice is None:
                raise BloomerError("invalid_choice", f"未知の選択肢です: {choice_key}")

            # 選択の効果を適用
            run.mood = _clamp(run.mood + choice.get("mood", 0))
            run.trust = _clamp(run.trust + choice.get("trust", 0))

            axes: dict[str, int] = _load_json(run.axes_json, {k: 50 for k in AXIS_KEYS})
            growth: dict[str, int] = _load_json(
                run.growth_json, {k: 0 for k in AXIS_KEYS}
            )
            for axis, gain in (choice.get("axes") or {}).items():
                if axis in AXIS_KEYS:
                    growth[axis] = _clamp(
                        growth.get(axis, 0) + gain,
                        AXIS_MIN - axes.get(axis, 0),
                        AXIS_MAX - axes.get(axis, 0),
                    )
            run.growth_json = _dump_json(growth)

            # フラグ記録
            decisions: dict[str, str] = _load_json(run.decisions_json, {})
            decisions[str(run.day)] = choice.get("flag", choice_key)
            run.decisions_json = _dump_json(decisions)

            event = BloomerEvent(
                id=str(uuid.uuid4()),
                run_id=run.id,
                day=run.day,
                kind="milestone",
                action_key=choice_key,
                payload_json=_dump_json(
                    {
                        "milestone_id": milestone.get("id"),
                        "flag": choice.get("flag"),
                        "mood_delta": choice.get("mood", 0),
                        "trust_delta": choice.get("trust", 0),
                        "axes": choice.get("axes", {}),
                    }
                ),
                narration=None,
            )
            db.add(event)
            await db.commit()
            await db.refresh(run)
            return {"run": run, "flag": choice.get("flag"), "event_id": event.id}

    # ------------------------------------------------------------------
    # 衣装変更
    # ------------------------------------------------------------------

    async def equip_outfit(
        self, run_id: str, user_id: str, outfit_key: str
    ) -> dict[str, Any]:
        outfit_def = OUTFIT_CATALOG.get(outfit_key)
        if outfit_def is None:
            raise BloomerError("invalid_outfit", f"未知の衣装です: {outfit_key}")

        async with async_session_factory() as db:
            result = await db.execute(
                select(BloomerRun).where(
                    BloomerRun.id == run_id, BloomerRun.user_id == user_id
                )
            )
            run = result.scalar_one_or_none()
            if run is None:
                raise BloomerError("not_found", "育成ランが見つかりません")
            if run.status != "active":
                raise BloomerError("run_ended", "このランはすでに終了しています")

            wardrobe: list[str] = _load_json(run.wardrobe_json, [])
            if outfit_key not in wardrobe:
                raise BloomerError("not_owned", f"{outfit_key} は所持していません")
            if run.stage < outfit_def.get("required_stage", 0):
                raise BloomerError(
                    "stage_locked",
                    f"{outfit_key} はステージ {outfit_def['required_stage']} 以降で着用できます",
                )
            required_nsfw = outfit_def.get("required_nsfw_stage", 0)
            if required_nsfw and run.nsfw_stage < required_nsfw:
                raise BloomerError(
                    "nsfw_locked",
                    f"{outfit_key} は NSFW 段階 {required_nsfw} 以降で着用できます",
                )

            run.equipped_outfit = outfit_key

            # 素質との相性による機嫌変化
            fit_axis = outfit_def.get("fit_axis")
            if fit_axis:
                axes: dict[str, int] = _load_json(run.axes_json, {})
                growth: dict[str, int] = _load_json(run.growth_json, {})
                effective = axes.get(fit_axis, 0) + growth.get(fit_axis, 0)
                if effective >= OUTFIT_FIT_THRESHOLD:
                    run.mood = _clamp(run.mood + OUTFIT_FIT_MOOD_HIGH)
                else:
                    run.mood = _clamp(run.mood + OUTFIT_FIT_MOOD_LOW)

            await db.commit()
            await db.refresh(run)
            return {"run": run, "outfit_key": outfit_key}

    # ------------------------------------------------------------------
    # 画像タグ生成（router の SSE から呼ぶ）
    # ------------------------------------------------------------------

    async def get_image_tags(self, run: BloomerRun, language: str = "ja") -> str:
        system_prompt, user_prompt = build_image_tags_prompt(run, language)
        try:
            result = await llm_service.generate_text(system_prompt, user_prompt)
            return result.content.strip()[:300]
        except LLMServiceError as exc:
            logger.warning("Image tag generation failed: %s", exc)
            return (
                f"{run.name}, stage {run.stage}, {run.equipped_outfit or 'plain dress'}"
            )

    # ------------------------------------------------------------------
    # 画像ファイル管理
    # ------------------------------------------------------------------

    def save_image(self, run_id: str, image_bytes: bytes) -> str:
        """画像を保存し、相対パスを返す。"""
        run_dir = self._images_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        stem = hashlib.sha1(image_bytes[:512]).hexdigest()[:8]
        filename = f"{stem}-{uuid.uuid4().hex[:4]}.png"
        (run_dir / filename).write_bytes(image_bytes)
        return str(Path("bloomer_images") / run_id / filename)

    def image_file(self, run_id: str, filename: str) -> Path:
        """パストラバーサルを防いでファイルパスを返す。"""
        safe_name = Path(filename).name
        path = self._images_dir / run_id / safe_name
        if not path.is_file():
            raise BloomerError("image_not_found", f"画像が見つかりません: {safe_name}")
        return path

    def resolve_stored_image_path(self, image_path: str | None) -> Path | None:
        """DB に保存された相対パスを実ファイル Path に解決する。

        対応:
        - bloomer_images/{run_id}/{file}
        - history_images/{file}
        - images/characters/{file}
        """
        if not image_path:
            return None
        normalized = image_path.replace("\\", "/").lstrip("/")
        parts = [p for p in normalized.split("/") if p and p not in (".", "..")]
        if not parts:
            return None

        data_root = settings.history_images_dir.parent
        backend_root = Path(__file__).resolve().parents[2]

        if parts[0] == "bloomer_images" and len(parts) >= 3:
            candidate = data_root.joinpath(*parts)
        elif parts[0] == "history_images":
            candidate = data_root.joinpath(*parts)
        elif parts[0] == "images" and len(parts) >= 2 and parts[1] == "characters":
            candidate = backend_root.joinpath(*parts)
        else:
            # 旧データ互換: data 配下を優先
            candidate = data_root.joinpath(*parts)
            if not candidate.is_file():
                candidate = backend_root.joinpath(*parts)

        try:
            resolved = candidate.resolve()
        except OSError:
            return None

        # 許可ルート外は拒否
        allowed_roots = (
            (data_root / "bloomer_images").resolve(),
            settings.history_images_dir.resolve(),
            (backend_root / "images" / "characters").resolve(),
        )
        if not any(
            resolved == root or root in resolved.parents for root in allowed_roots
        ):
            return None
        return resolved if resolved.is_file() else None

    def character_image_file(self, filename: str) -> Path:
        """プリセットキャラ画像を安全に解決する。"""
        safe_name = Path(filename).name
        if not safe_name or safe_name != filename.replace("\\", "/").split("/")[-1]:
            raise BloomerError("image_not_found", "不正なファイル名です")
        base = Path(__file__).resolve().parents[2] / "images" / "characters"
        path = (base / safe_name).resolve()
        if base.resolve() not in path.parents and path != base.resolve():
            raise BloomerError("image_not_found", "不正なパスです")
        if not path.is_file():
            raise BloomerError("image_not_found", f"画像が見つかりません: {safe_name}")
        return path

    async def update_current_image(
        self, run_id: str, user_id: str, image_path: str
    ) -> None:
        async with async_session_factory() as db:
            result = await db.execute(
                select(BloomerRun).where(
                    BloomerRun.id == run_id, BloomerRun.user_id == user_id
                )
            )
            run = result.scalar_one_or_none()
            if run is None:
                raise BloomerError("not_found", "育成ランが見つかりません")
            run.current_image_path = image_path
            await db.commit()

    # ------------------------------------------------------------------
    # 初期軸 / 初期画像解決
    # ------------------------------------------------------------------

    async def _compute_initial_axes(
        self,
        user_id: str,
        source_session_id: str | None,
        character_id: str | None,
    ) -> dict[str, int]:
        """セッション引き継ぎなら 6 軸素質を算出。新規なら 50 基準のランダム。"""
        if source_session_id is not None:
            try:
                from .bloomer_lexicon_loader import get_bloomer_lexicon
                from .bloomer_stats_service import build_base_stats

                source = await self._build_fighter_source(source_session_id)
                result = build_base_stats(source, get_bloomer_lexicon())
                return result["axes"]
            except BloomerError:
                raise
            except Exception as exc:
                logger.warning(
                    "Failed to compute axes from session, using defaults: %s", exc
                )

        # プリセット or フォールバック: ランダム初期値
        rng = random.Random()
        axes: dict[str, int] = {}
        for key in AXIS_KEYS:
            axes[key] = rng.randint(30, 70)
        return axes

    async def _build_fighter_source(self, session_id: str) -> Any:
        from ..consts.bloomer_consts import MAX_CONVERSATION_SCAN, MAX_HISTORY_SCAN
        from ..databases.models import TransformationTag as TransformationTagORM
        from .bloomer_stats_service import (
            ConversationRecord,
            FighterSource,
            HistoryRecord,
            StatsRecord,
        )

        session = await session_store.get_session_by_id(session_id)
        if session is None:
            raise BloomerError("not_found", f"セッションが見つかりません: {session_id}")

        histories_raw = await session_store.get_history(session_id)
        if len(histories_raw) > MAX_HISTORY_SCAN:
            histories_raw = histories_raw[-MAX_HISTORY_SCAN:]

        history_ids = [h.id for h in histories_raw]
        tag_by_history: dict[str, Any] = {}
        if history_ids:
            async with async_session_factory() as db:
                tag_result = await db.execute(
                    select(TransformationTagORM).where(
                        TransformationTagORM.history_id.in_(history_ids)
                    )
                )
                for tag in tag_result.scalars().all():
                    tag_by_history[tag.history_id] = tag

        histories = []
        for history in histories_raw:
            tag = tag_by_history.get(history.id)
            histories.append(
                HistoryRecord(
                    instruction=history.instruction or "",
                    feeling_text=history.feeling_text,
                    after_description=history.after_description,
                    instruction_type=history.instruction_type,
                    costume_category=tag.costume_category if tag else None,
                    exposure_level=tag.exposure_level if tag else None,
                )
            )

        conversations_raw = await session_store.get_conversation_history(
            session_id, limit=MAX_CONVERSATION_SCAN
        )
        conversations = [
            ConversationRecord(
                role=message.role or "assistant",
                content=message.content or "",
            )
            for message in conversations_raw
        ]

        stats = await session_store.get_session_stats(session_id)
        stats_record: StatsRecord | None = None
        if stats is not None:
            stats_record = StatsRecord(
                bloom=stats.bloom,
                shame=stats.shame,
                adaptation=stats.adaptation,
            )

        attribute_texts = await session_store.get_session_attribute_texts(session_id)
        self_mode = bool(session.self_mode)
        self_profile = None
        if self_mode:
            self_profile = await session_store.get_self_profile(session.user_id)

        return FighterSource(
            session_id=session_id,
            self_mode=self_mode,
            transformation_count=session.transformation_count or 0,
            source_history_id=None,
            histories=histories,
            conversations=conversations,
            attribute_texts=attribute_texts,
            stats=stats_record,
            self_profile=self_profile,
        )

    async def _resolve_initial_image(
        self,
        user_id: str,
        source_session_id: str | None,
        character_id: str | None,
    ) -> str | None:
        if source_session_id:
            async with async_session_factory() as db:
                result = await db.execute(
                    select(History)
                    .where(History.session_id == source_session_id)
                    .order_by(History.created_at.desc())
                    .limit(1)
                )
                latest = result.scalar_one_or_none()
                if latest and latest.image_path:
                    return latest.image_path

        if character_id:
            # characters.json から image_path を解決する
            try:
                chars_path = (
                    Path(__file__).resolve().parents[2]
                    / "images"
                    / "characters"
                    / "characters.json"
                )
                chars = json.loads(chars_path.read_text(encoding="utf-8"))
                for ch in chars:
                    if ch.get("id") == character_id:
                        return ch.get("image_path")
                # character_id が見つからなければ先頭エントリを使う
                if chars:
                    return chars[0].get("image_path")
            except Exception as exc:
                logger.warning("Failed to resolve character preset image: %s", exc)

        return None

    # ------------------------------------------------------------------
    # LLM ユーティリティ
    # ------------------------------------------------------------------

    async def _safe_narrate(self, system_prompt: str, user_prompt: str) -> str | None:
        try:
            result = await llm_service.generate_text(system_prompt, user_prompt)
            return result.content.strip()[:MAX_NARRATION_LENGTH]
        except LLMServiceError as exc:
            logger.warning("Bloomer narration failed: %s", exc)
            return None


bloomer_service = BloomerService()
