"""Integration tests for /game/characters/generate-tags (spec 005, T015)."""

from __future__ import annotations

import importlib
from typing import Any, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.services.llm_service import LLMServiceError

character_router_module = importlib.import_module("gateway.routes.character_router")
character_router = character_router_module.router


class _StubLLM:
    def __init__(self, return_values=None, fail_with=None):
        self.calls: List[Any] = []
        self._returns = return_values or []
        self._fail_with = fail_with

    async def generate_character_tags_batch(self, items, *, provider_override=None):
        self.calls.append(list(items))
        if self._fail_with is not None:
            raise self._fail_with
        return [{"id": i["id"], "tags": "blue eyes, short hair"} for i in items]


def _make_app(stub):
    monkey = pytest.MonkeyPatch()
    monkey.setattr(character_router_module, "llm_service", stub)
    app = FastAPI()
    app.include_router(character_router, prefix="/api")
    return app, monkey


def test_generate_tags_n2_single_call():
    stub = _StubLLM()
    app, monkey = _make_app(stub)
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/game/characters/generate-tags",
                json={
                    "items": [
                        {"id": "a", "name": "Alice", "natural": "金髪"},
                        {"id": "b", "name": "Bob", "natural": "黒髪"},
                    ]
                },
            )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert [r["id"] for r in results] == ["a", "b"]
        assert len(stub.calls) == 1
        assert len(stub.calls[0]) == 2
    finally:
        monkey.undo()


def test_generate_tags_n4_single_call():
    stub = _StubLLM()
    app, monkey = _make_app(stub)
    try:
        with TestClient(app) as client:
            payload = {
                "items": [
                    {"id": str(i), "name": f"C{i}", "natural": "x"} for i in range(4)
                ]
            }
            resp = client.post("/api/game/characters/generate-tags", json=payload)
        assert resp.status_code == 200
        assert len(stub.calls) == 1
        assert len(stub.calls[0]) == 4
    finally:
        monkey.undo()


def test_generate_tags_llm_failure_returns_502():
    stub = _StubLLM(fail_with=LLMServiceError("parse_failed"))
    app, monkey = _make_app(stub)
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/game/characters/generate-tags",
                json={"items": [{"id": "a", "name": "A", "natural": "x"}]},
            )
        assert resp.status_code == 502
        assert resp.json()["detail"]["code"] == "llm_failure"
    finally:
        monkey.undo()
