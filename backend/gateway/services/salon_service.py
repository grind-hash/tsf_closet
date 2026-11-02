"""Salon management mode (サロン経営モード).

A salon run is one season: each week customers book, the player serves them,
and closing the week pays the fixed costs. Serving a customer is an ordinary
game session with a request (the shared request foundation, with a 3-turn
limit and 2 counselling questions); this module adds only the visit (booking,
checkout, review) and the management (cash, reputation, weekly settlement).
"""

from __future__ import annotations

import json
import logging
import random
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select

from ..consts.salon import (
    SALON_BASE_PRICE,
    SALON_DEFAULT_DIFFICULTY,
    SALON_DIFFICULTY_INITIAL_CASH,
    SALON_EXTRA_TURN_PRICE,
    SALON_EXTRA_TURNS_MAX,
    SALON_HINT_EMPHASIS_DIFFICULTIES,
    SALON_INITIAL_REPUTATION,
    SALON_NAME_MAX,
    SALON_QUESTION_LIMIT,
    SALON_REVIEW_MAX,
    SALON_TOTAL_WEEKS,
    SALON_TURN_LIMIT,
    SALON_WEEKLY_FIXED_COST,
    SALON_WEEKLY_SALARY,
)
from ..databases.base import async_session_factory
from ..databases.models import SalonRun, SalonVisit
from .achievement_service import achievement_service
from .achievements import (
    ACHIEVEMENTS,
    check_achievement,
    get_global_stats,
    get_user_achievements,
)
from .characters import character_manager
from .clothing_layers import split_worn_under_layers
from .cost_tracker import begin_cost_tracking
from .custom_sessions import list_custom_character_profiles
from .game_service import GameServiceError, game_service
from .preset_sessions import list_salon_preset_customers
from .salon_prompts import (
    build_salon_review_prompt,
    fallback_salon_review,
    returning_visit_summary,
)
from .salon_rules import (
    Customer,
    bookings_count,
    clamp_reputation,
    declined_reputation_delta,
    keeps_look,
    pick_customers,
    season_result,
    visit_payment,
    visit_reputation_delta,
    week_summary,
)
from .session import DEFAULT_USER_ID, session_store
from .session_branch_service import SessionBranchError, branch_session_from_history
from .session_request_service import (
    SessionRequestError,
    experience_bonus,
    generate_customer_text,
    session_profile,
    session_request_service,
    with_experience,
)

logger = logging.getLogger(__name__)


class SalonError(Exception):
    """サロンの操作を受け付けられないときの例外。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def _customer_pool(db: Any) -> list[Customer]:
    """予約に入りうるお客様: 同梱のテンプレートキャラ、保存済みのカスタムキャラ、
    来店する設定で立ち絵のあるキャラクター(キャラクター画面で作ったキャラ)。"""
    pool = [
        Customer("template", character.id, character.name)
        for character in character_manager.get_all()
    ]
    pool.extend(
        Customer("custom", str(profile["id"]), str(profile.get("name") or ""))
        for profile in list_custom_character_profiles()
    )
    pool.extend(
        Customer("preset", item["id"], item["name"])
        for item in await list_salon_preset_customers(db)
    )
    return pool


def _load_state(run: SalonRun) -> dict[str, Any]:
    try:
        state = json.loads(run.state_json or "{}")
    except (TypeError, ValueError):
        state = {}
    return state if isinstance(state, dict) else {}


def _initial_cash(state: dict[str, Any]) -> int:
    """開店時の開業資金。決算の成功の線になる。"""
    default = SALON_DIFFICULTY_INITIAL_CASH[SALON_DEFAULT_DIFFICULTY]
    return int(state.get("initial_cash", default))


def _serialize_visit(visit: SalonVisit, visits: list[SalonVisit]) -> dict[str, Any]:
    """来店1件。常連は同じお客様の何回目の来店かと、前回の口コミを添える。"""
    same_customer = [
        item
        for item in visits
        if item.customer_source == visit.customer_source
        and item.customer_id == visit.customer_id
        and (item.week, item.slot) < (visit.week, visit.slot)
    ]
    previous_reviews = [
        item.review for item in same_customer if item.status == "done" and item.review
    ]
    return {
        "id": visit.id,
        "week": visit.week,
        "slot": visit.slot,
        "customer": {
            "source": visit.customer_source,
            "id": visit.customer_id,
            "name": visit.customer_name,
        },
        "session_id": visit.session_id,
        "status": visit.status,
        "satisfaction": visit.satisfaction,
        "fulfilled": bool(visit.fulfilled),
        "payment": int(visit.payment or 0),
        "reputation_delta": int(visit.reputation_delta or 0),
        "review": visit.review,
        "visit_number": len(same_customer) + 1,
        "previous_review": previous_reviews[-1] if previous_reviews else None,
        "kept_look": visit.kept_history_id is not None,
        "returning_look": visit.start_history_id is not None,
        "experience_bonus": int(visit.experience_bonus or 0),
        "extra_cost": int(visit.extra_cost or 0),
    }


def _serialize_run(run: SalonRun, visits: list[SalonVisit]) -> dict[str, Any]:
    state = _load_state(run)
    ordered = sorted(visits, key=lambda item: (item.week, item.slot))
    return {
        "id": run.id,
        "name": run.name,
        "status": run.status,
        "week": run.week,
        "total_weeks": run.total_weeks,
        "cash": run.cash,
        "reputation": run.reputation,
        "difficulty": state.get("difficulty", SALON_DEFAULT_DIFFICULTY),
        "initial_cash": _initial_cash(state),
        "sensitive": bool(state.get("sensitive", False)),
        "weekly_fixed_cost": SALON_WEEKLY_FIXED_COST,
        "weekly_salary": SALON_WEEKLY_SALARY,
        "base_price": SALON_BASE_PRICE,
        "turn_limit": SALON_TURN_LIMIT,
        "question_limit": SALON_QUESTION_LIMIT,
        "extra_turn_price": SALON_EXTRA_TURN_PRICE,
        "extra_turns_max": SALON_EXTRA_TURNS_MAX,
        "visits": [_serialize_visit(item, ordered) for item in ordered],
        "weeks": list(state.get("weeks", [])),
        "result": state.get("result"),
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
    }


def _unlock_salon_achievements() -> list[dict[str, Any]]:
    """決算で条件を満たしたサロン経営の実績を保存し、通知用に返す。

    判定に失敗しても週の締めは止めない(次の決算で改めて判定される)。
    """
    try:
        already = {
            status.achievement_id
            for status in get_user_achievements()
            if status.unlocked
        }
        stats = get_global_stats()
        unlocked = []
        for achievement in ACHIEVEMENTS.values():
            if achievement.category != "salon" or achievement.id in already:
                continue
            if not check_achievement(achievement, stats):
                continue
            achievement_service.save_user_achievement(achievement.id)
            unlocked.append(
                {
                    "achievement_id": achievement.id,
                    "name": achievement.name,
                    "description": achievement.description,
                    "icon": achievement.icon,
                    "category": achievement.category,
                }
            )
        return unlocked
    except Exception as error:
        logger.warning(
            "Salon achievement check failed: %s: %s", type(error).__name__, error
        )
        return []


class SalonService:
    async def _load(self, db: Any, run_id: str) -> tuple[SalonRun, list[SalonVisit]]:
        run = await db.get(SalonRun, run_id)
        if run is None or run.user_id != DEFAULT_USER_ID:
            raise SalonError("salon_not_found", "サロンが見つかりません")
        visits = list(
            (
                await db.execute(
                    select(SalonVisit).where(SalonVisit.salon_id == run_id)
                )
            ).scalars()
        )
        return run, visits

    @staticmethod
    def _find_visit(visits: list[SalonVisit], visit_id: str) -> SalonVisit:
        visit = next((item for item in visits if item.id == visit_id), None)
        if visit is None:
            raise SalonError("visit_not_found", "予約が見つかりません")
        return visit

    @staticmethod
    def _require_active(run: SalonRun) -> None:
        if run.status != "active":
            raise SalonError("salon_closed", "このサロンのシーズンは終わっています")

    @staticmethod
    async def _book_week(
        db: Any, run: SalonRun, kept: Sequence[SalonVisit] = ()
    ) -> None:
        """run.week の予約を評判に応じて入れる。

        kept は前の週に施術した姿のまま帰ったお客様の来店で、必ず予約に入れ、
        残りの枠を抽選で埋める。
        """
        fresh = pick_customers(
            await _customer_pool(db),
            seed=run.seed,
            week=run.week,
            count=bookings_count(run.reputation) - len(kept),
            exclude={(item.customer_source, item.customer_id) for item in kept},
        )
        bookings = [
            (
                Customer(item.customer_source, item.customer_id, item.customer_name),
                item.kept_history_id,
            )
            for item in kept
        ] + [(customer, None) for customer in fresh]
        for slot, (customer, start_history_id) in enumerate(bookings):
            db.add(
                SalonVisit(
                    id=str(uuid.uuid4()),
                    salon_id=run.id,
                    week=run.week,
                    slot=slot,
                    customer_source=customer.source,
                    customer_id=customer.id,
                    customer_name=customer.name,
                    status="booked",
                    start_history_id=start_history_id,
                )
            )

    async def list_runs(self) -> list[dict[str, Any]]:
        async with async_session_factory() as db:
            runs = list(
                (
                    await db.execute(
                        select(SalonRun)
                        .where(SalonRun.user_id == DEFAULT_USER_ID)
                        .order_by(SalonRun.updated_at.desc())
                    )
                ).scalars()
            )
            result = []
            for run in runs:
                _, visits = await self._load(db, run.id)
                result.append(_serialize_run(run, visits))
            return result

    async def get_run(self, run_id: str) -> dict[str, Any]:
        async with async_session_factory() as db:
            run, visits = await self._load(db, run_id)
            return _serialize_run(run, visits)

    async def create_run(
        self,
        name: str,
        difficulty: str = SALON_DEFAULT_DIFFICULTY,
        *,
        sensitive: bool = False,
    ) -> dict[str, Any]:
        """開店する。開業資金は経営の難易度で決まる。1週目の予約も入れる。

        sensitive は過激施術の初期値(開店画面が直近のサロンの設定を引き継いで渡す)。
        """
        clean_name = " ".join(str(name or "").split())[:SALON_NAME_MAX]
        if not clean_name:
            raise SalonError("empty_name", "サロンの名前を入力してください")
        initial_cash = SALON_DIFFICULTY_INITIAL_CASH.get(difficulty)
        if initial_cash is None:
            raise SalonError("invalid_difficulty", "経営の難易度が正しくありません")
        now = datetime.now()
        run = SalonRun(
            id=str(uuid.uuid4()),
            user_id=DEFAULT_USER_ID,
            name=clean_name,
            status="active",
            week=1,
            total_weeks=SALON_TOTAL_WEEKS,
            cash=initial_cash,
            reputation=SALON_INITIAL_REPUTATION,
            seed=random.randint(1, 2**31 - 1),
            state_json=json.dumps(
                {
                    "difficulty": difficulty,
                    "initial_cash": initial_cash,
                    "sensitive": bool(sensitive),
                    "weeks": [],
                }
            ),
            created_at=now,
            updated_at=now,
        )
        async with async_session_factory() as db:
            db.add(run)
            await db.flush()
            await self._book_week(db, run)
            await db.commit()
        return await self.get_run(run.id)

    async def update_settings(self, run_id: str, *, sensitive: bool) -> dict[str, Any]:
        """オーナー室の設定を変える。依頼は接客の開始時に作るので、次の接客から効く。"""
        async with async_session_factory() as db:
            run, visits = await self._load(db, run_id)
            self._require_active(run)
            state = _load_state(run)
            state["sensitive"] = bool(sensitive)
            run.state_json = json.dumps(state)
            run.updated_at = datetime.now()
            await db.commit()
            return _serialize_run(run, visits)

    async def delete_run(self, run_id: str) -> None:
        async with async_session_factory() as db:
            run, _ = await self._load(db, run_id)
            await db.delete(run)
            await db.commit()

    async def start_visit(
        self, run_id: str, visit_id: str, *, language: str
    ) -> dict[str, Any]:
        """接客を始める。依頼付きのセッションを作り、来店に紐づける。

        接客中の来店なら、作り直さずにそのセッションを返す(画面から離れて戻ったとき)。
        """
        async with async_session_factory() as db:
            run, visits = await self._load(db, run_id)
            self._require_active(run)
            visit = self._find_visit(visits, visit_id)
            if visit.week != run.week:
                raise SalonError("not_this_week", "今週の予約ではありません")
            if visit.status == "serving" and visit.session_id:
                # 通常画面で別のセッションを始めていても、接客中のお客様に戻す
                await session_store.activate_session(visit.session_id)
                request = await session_request_service.get_request_view(
                    visit.session_id
                )
                return {
                    "session_id": visit.session_id,
                    "request": request,
                    "run": _serialize_run(run, visits),
                    "cost_usd": None,
                }
            if visit.status != "booked":
                raise SalonError("visit_closed", "この予約は接客を終えています")
            if any(item.status == "serving" for item in visits if item.id != visit.id):
                raise SalonError(
                    "serving_other", "先に、接客中のお客様の会計を済ませてください"
                )
            customer = visit.customer_source, visit.customer_id
            state = _load_state(run)
            difficulty = state.get("difficulty", SALON_DEFAULT_DIFFICULTY)
            sensitive_setting = bool(state.get("sensitive", False))
            start_history_id = visit.start_history_id
            previous = next(
                (
                    item
                    for item in visits
                    if start_history_id and item.kept_history_id == start_history_id
                ),
                None,
            )
            previous_visit_info = (
                (previous.session_id, previous.review) if previous else (None, None)
            )

        # 過激施術は NSFW モード(成人向けの元スイッチ)が ON のときだけ効く
        user_settings = await session_store.get_user_settings()
        adult = sensitive_setting and bool(user_settings.get("nsfw_mode"))
        try:
            session = None
            previous_visit = None
            if start_history_id:
                session = await self._branch_kept_look(start_history_id, language)
            if session is not None:
                previous_visit = await self._previous_visit_context(
                    *previous_visit_info
                )
            elif customer[0] == "template":
                session, _, _ = await game_service.start_session(
                    character_id=customer[1],
                    difficulty="normal",
                    nsfw_mode=adult,
                    self_mode=False,
                )
            elif customer[0] == "preset":
                session, _, _ = await game_service.start_preset_session(
                    preset_id=customer[1],
                    difficulty="normal",
                    nsfw_mode=adult,
                    self_mode=False,
                )
            else:
                session, _, _ = await game_service.start_custom_session(
                    custom_character_id=customer[1],
                    image=None,
                    name="",
                    description="",
                    pronoun="",
                    personality="",
                    gender=None,
                    base_tags="",
                    difficulty="normal",
                    nsfw_mode=adult,
                    self_mode=False,
                    use_saved_profile=True,
                )
            request, cost_usd = await session_request_service.create_request(
                session.id,
                language=language,
                turn_limit=SALON_TURN_LIMIT,
                question_limit=SALON_QUESTION_LIMIT,
                emphasize_hints=difficulty in SALON_HINT_EMPHASIS_DIFFICULTIES,
                previous_visit=previous_visit,
                sensitive=adult,
            )
        except (GameServiceError, SessionRequestError) as error:
            raise SalonError("start_failed", str(error)) from error

        async with async_session_factory() as db:
            run, visits = await self._load(db, run_id)
            visit = self._find_visit(visits, visit_id)
            if visit.status != "booked":
                # 二重送信などで、先に別の呼び出しが接客を始めていた
                raise SalonError("visit_closed", "この予約は接客を始めています")
            visit.session_id = session.id
            visit.status = "serving"
            visit.updated_at = datetime.now()
            run.updated_at = datetime.now()
            await db.commit()
            return {
                "session_id": session.id,
                "request": request,
                "run": _serialize_run(run, visits),
                "cost_usd": cost_usd or None,
            }

    @staticmethod
    async def _branch_kept_look(history_id: str, language: str) -> Any | None:
        """前回持ち帰った姿から、接客用のセッションを分岐して作る。

        前回のセッションや画像が消えていて分岐できなければ None(元の姿から始める)。
        """
        try:
            branched = await branch_session_from_history(
                history_id,
                inherit_stats=True,
                self_mode=False,
                language=language,
                summary=returning_visit_summary(language),
            )
        except SessionBranchError as error:
            logger.info("Salon kept look is unavailable: %s", error.code)
            return None
        return await session_store.get_session_by_id(branched.session_id)

    @staticmethod
    async def _previous_visit_context(
        session_id: str | None, review: str | None
    ) -> dict[str, Any]:
        """前回の来店の願いと口コミ。依頼の生成で、追加の要望の手掛かりにする。"""
        request = (
            await session_store.get_session_request(session_id) if session_id else None
        )
        return {"wish": (request or {}).get("wish") or "", "review": review or ""}

    async def checkout_visit(
        self, run_id: str, visit_id: str, *, language: str
    ) -> dict[str, Any]:
        """会計する。土台の満足度から支払と評判を決め、口コミを書いてもらう。"""
        async with async_session_factory() as db:
            run, visits = await self._load(db, run_id)
            self._require_active(run)
            visit = self._find_visit(visits, visit_id)
            if visit.status != "serving" or not visit.session_id:
                raise SalonError("not_serving", "接客中のお客様ではありません")
            session_id = visit.session_id
            week, total_weeks = run.week, run.total_weeks

        request = await session_request_service.get_request_view(session_id)
        if request is None:
            raise SalonError("request_missing", "依頼が見つかりません")
        if int(request.get("turns_used") or 0) == 0:
            raise SalonError("not_served", "まだ施術をしていません")
        # お披露目の体験の場面は施術ではない(依頼の評価が付かない最後の手番)
        styled = await session_store.get_latest_evaluated_history(session_id)
        latest = await session_store.get_latest_history(session_id)
        sensitive = bool(request.get("sensitive"))
        experienced = (
            sensitive
            and latest is not None
            and styled is not None
            and latest.id != styled.id
        )
        experience_feeling = (latest.feeling_text or "") if experienced else ""
        # 体験してみたら思ったより良かった、を満足度に入れる。施術の満足度は土台が決め、
        # 体験の加点で依頼達成の線を越えたら、達成として扱う
        bonus = experience_bonus(experienced)
        satisfaction = with_experience(
            int(request.get("satisfaction") or 0), experienced
        )
        fulfilled = request.get("status") == "fulfilled"
        if not fulfilled and satisfaction >= int(request.get("threshold") or 0) > 0:
            fulfilled = True
            if styled is not None:
                await session_store.mark_session_request_fulfilled(
                    session_id, styled.id
                )
        payment = visit_payment(satisfaction, fulfilled)
        delta = visit_reputation_delta(satisfaction, fulfilled)
        # 願いを叶えたお客様は、最後の施術の姿のまま帰り、翌週もその姿で来る。
        # 体験の場面は持ち帰る姿にしない
        kept_history_id = (
            styled.id
            if styled is not None and keeps_look(fulfilled, week, total_weeks)
            else None
        )

        tracker = begin_cost_tracking()
        review = await self._write_review(
            session_id,
            wish=str(request.get("wish") or ""),
            satisfaction=satisfaction,
            fulfilled=fulfilled,
            language=language,
            keeps_look=kept_history_id is not None,
            final_history=styled or latest,
            sensitive=sensitive,
            experience_feeling=experience_feeling,
        )

        async with async_session_factory() as db:
            run, visits = await self._load(db, run_id)
            visit = self._find_visit(visits, visit_id)
            if visit.status != "serving":
                raise SalonError("not_serving", "接客中のお客様ではありません")
            visit.status = "done"
            visit.satisfaction = satisfaction
            visit.fulfilled = fulfilled
            visit.payment = payment
            visit.reputation_delta = delta
            visit.review = review
            visit.kept_history_id = kept_history_id
            visit.experience_bonus = bonus
            visit.updated_at = datetime.now()
            run.cash += payment
            run.reputation = clamp_reputation(run.reputation + delta)
            run.updated_at = datetime.now()
            await db.commit()
            result = {
                "run": _serialize_run(run, visits),
                "visit": _serialize_visit(visit, visits),
                "cost_usd": tracker.total_usd or None,
            }
        # 接客を終えたお客様を、通常のプレイ画面で開いたままにしない
        active = await session_store.get_active_session()
        if active is not None and active.id == session_id:
            await session_store.reset_session()
        return result

    async def _write_review(
        self,
        session_id: str,
        *,
        wish: str,
        satisfaction: int,
        fulfilled: bool,
        language: str,
        keeps_look: bool = False,
        final_history: Any | None = None,
        sensitive: bool = False,
        experience_feeling: str = "",
    ) -> str:
        """お客様本人の口調で口コミを書かせる。失敗したら定型文にする。

        final_history は仕上がった姿の履歴(最後の施術の手番)。
        """
        try:
            profile = await session_profile(session_id) or {}
            final_look = split_worn_under_layers(
                (final_history.after_description or "") if final_history else ""
            )[0]
            user_settings = await session_store.get_user_settings()
            system_prompt, user_prompt = build_salon_review_prompt(
                profile=profile,
                wish=wish,
                satisfaction=satisfaction,
                fulfilled=fulfilled,
                final_look=final_look,
                language=language,
                keeps_look=keeps_look,
                sensitive=sensitive,
                experience_feeling=experience_feeling,
            )
            raw = await generate_customer_text(
                system_prompt,
                user_prompt,
                novelai_model=user_settings.get("novelai_text_model"),
            )
            review = " ".join(raw.strip().strip('「」"').split())[:SALON_REVIEW_MAX]
            if review:
                return review
        except Exception as error:
            logger.warning(
                "Salon review generation failed: %s: %s", type(error).__name__, error
            )
        return fallback_salon_review(satisfaction, fulfilled, language)

    async def buy_extra_turn(self, run_id: str, visit_id: str) -> dict[str, Any]:
        """資金を払って施術を1手足す。手数を使い切った接客中の来店だけ、来店1回につき上限まで。

        代金はその場で現金から引く(足りなければ買えない)。{run, request} を返す。
        """
        async with async_session_factory() as db:
            run, visits = await self._load(db, run_id)
            self._require_active(run)
            visit = self._find_visit(visits, visit_id)
            if visit.status != "serving" or not visit.session_id:
                raise SalonError("not_serving", "接客中のお客様ではありません")
            if (
                int(visit.extra_cost or 0)
                >= SALON_EXTRA_TURN_PRICE * SALON_EXTRA_TURNS_MAX
            ):
                raise SalonError("extra_turn_limit", "追加の施術はこれ以上できません")
            if run.cash < SALON_EXTRA_TURN_PRICE:
                raise SalonError("insufficient_cash", "追加の施術の代金が足りません")
            session_id = visit.session_id

        request = await session_request_service.get_request_view(session_id)
        if request is None:
            raise SalonError("request_missing", "依頼が見つかりません")
        if request.get("turns_remaining") != 0:
            raise SalonError("turns_left", "施術の手数を使い切ってから追加してください")

        async with async_session_factory() as db:
            run, visits = await self._load(db, run_id)
            visit = self._find_visit(visits, visit_id)
            if (
                visit.status != "serving"
                or int(visit.extra_cost or 0)
                >= SALON_EXTRA_TURN_PRICE * SALON_EXTRA_TURNS_MAX
                or run.cash < SALON_EXTRA_TURN_PRICE
            ):
                raise SalonError("extra_turn_limit", "追加の施術はこれ以上できません")
            visit.extra_cost = int(visit.extra_cost or 0) + SALON_EXTRA_TURN_PRICE
            visit.updated_at = datetime.now()
            run.cash -= SALON_EXTRA_TURN_PRICE
            run.updated_at = datetime.now()
            await db.commit()
            serialized = _serialize_run(run, visits)
        await session_store.extend_session_request_turn_limit(session_id)
        return {
            "run": serialized,
            "request": await session_request_service.get_request_view(session_id),
        }

    async def decline_visit(self, run_id: str, visit_id: str) -> dict[str, Any]:
        """予約を断る。評判が少し下がる。"""
        async with async_session_factory() as db:
            run, visits = await self._load(db, run_id)
            self._require_active(run)
            visit = self._find_visit(visits, visit_id)
            if visit.status != "booked":
                raise SalonError("visit_closed", "この予約は断れません")
            delta = declined_reputation_delta()
            visit.status = "declined"
            visit.reputation_delta = delta
            visit.updated_at = datetime.now()
            run.reputation = clamp_reputation(run.reputation + delta)
            run.updated_at = datetime.now()
            await db.commit()
            return _serialize_run(run, visits)

    async def close_week(self, run_id: str) -> dict[str, Any]:
        """週を締め、{run, achievements} を返す。

        接客していない予約は断ったものとして扱い、固定費と本業の収入を反映する。
        現金がマイナスなら倒産、最終週なら決算し、それ以外は翌週の予約を入れる。
        決算したときは、サロン経営の実績を判定する。
        """
        async with async_session_factory() as db:
            run, visits = await self._load(db, run_id)
            self._require_active(run)
            this_week = [item for item in visits if item.week == run.week]
            if any(item.status == "serving" for item in this_week):
                raise SalonError(
                    "serving_open",
                    "接客中のお客様の会計を済ませてから週を締めてください",
                )
            now = datetime.now()
            for visit in this_week:
                if visit.status == "booked":
                    visit.status = "declined"
                    visit.reputation_delta = declined_reputation_delta()
                    visit.updated_at = now
                    run.reputation = clamp_reputation(
                        run.reputation + visit.reputation_delta
                    )
            summary = week_summary(
                week=run.week,
                cash_before_close=run.cash,
                reputation=run.reputation,
                payments=[
                    int(item.payment or 0)
                    for item in this_week
                    if item.status == "done"
                ],
                served=sum(1 for item in this_week if item.status == "done"),
                declined=sum(1 for item in this_week if item.status == "declined"),
                extra_costs=[int(item.extra_cost or 0) for item in this_week],
            )
            run.cash = summary["cash_end"]
            state = _load_state(run)
            state["weeks"] = [*state.get("weeks", []), summary]
            if run.cash < 0:
                run.status = "bankrupt"
                state["result"] = {"outcome": "bankrupt", "cash": run.cash}
            elif run.week >= run.total_weeks:
                run.status = "completed"
                initial_cash = _initial_cash(state)
                state["result"] = {
                    "outcome": season_result(run.cash, initial_cash),
                    "cash": run.cash,
                    "profit": run.cash - initial_cash,
                }
            else:
                run.week += 1
                kept = [
                    item
                    for item in this_week
                    if item.status == "done" and item.kept_history_id
                ]
                await self._book_week(db, run, kept)
            run.state_json = json.dumps(state, ensure_ascii=False)
            run.updated_at = now
            await db.commit()
            run, visits = await self._load(db, run_id)
            serialized = _serialize_run(run, visits)
        achievements = (
            _unlock_salon_achievements() if serialized["status"] == "completed" else []
        )
        return {"run": serialized, "achievements": achievements}


salon_service = SalonService()
