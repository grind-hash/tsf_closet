import importlib
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.services import memory_job_service as memory_job_module
from gateway.services.memory_job_service import MemoryJobService, MemoryJobState
from gateway.services.memory_prompts import (
    build_memory_generation_user_prompt,
    build_memory_merge_user_prompt,
    get_memory_generation_system_prompt,
    get_memory_merge_system_prompt,
)

memory_router = importlib.import_module("gateway.routes.memory_router")


@pytest.mark.asyncio
async def test_generation_records_exact_prompts_and_results(monkeypatch):
    service = MemoryJobService()
    job = MemoryJobState(
        job_id="12345678-test-job",
        total=2,
        regenerate_existing=False,
        language="ja",
        started_at=datetime(2026, 7, 13, 10, 30, 0),
    )
    service._jobs[job.job_id] = job
    summaries = [
        {"title": "称号1", "summary": "要約1", "timeline": []},
        {"title": "称号2", "summary": "要約2", "timeline": []},
    ]
    chunks = [[summaries[0]], [summaries[1]]]
    calls: list[tuple[str, str]] = []
    saved_texts: list[str] = []

    async def generate_text(system_prompt: str, user_prompt: str) -> str:
        calls.append((system_prompt, user_prompt))
        return f"応答{len(calls)}"

    async def save_memory_text(memory_text: str) -> str:
        saved_texts.append(memory_text)
        return memory_text

    monkeypatch.setattr(memory_job_module, "chunk_summaries", lambda _: chunks)
    monkeypatch.setattr(service, "_generate_text_with_retry", generate_text)
    monkeypatch.setattr(
        memory_job_module.settings_service,
        "save_memory_text",
        save_memory_text,
    )

    await service._generate_and_save_memory_text(job, summaries, "ja")

    chunk_system_prompt = get_memory_generation_system_prompt("ja")
    expected_chunk_calls = [
        (
            chunk_system_prompt,
            build_memory_generation_user_prompt(chunk, "ja"),
        )
        for chunk in chunks
    ]
    expected_merge_call = (
        get_memory_merge_system_prompt("ja"),
        build_memory_merge_user_prompt(["応答1", "応答2"], "ja"),
    )
    assert calls == [*expected_chunk_calls, expected_merge_call]
    assert saved_texts == ["応答3"]
    assert [snapshot.status for snapshot in job.memory_prompt_snapshots] == [
        "completed",
        "completed",
    ]
    assert [snapshot.response for snapshot in job.memory_prompt_snapshots] == [
        "応答1",
        "応答2",
    ]
    assert job.merge_prompt_snapshot is not None
    assert job.merge_prompt_snapshot.status == "completed"
    assert job.merge_prompt_snapshot.response == "応答3"

    export = service.get_job_analysis_export(job.job_id)
    assert export is not None
    content, filename = export
    assert filename == "memory-analysis-2026-07-13-103000-12345678.md"
    assert "### Chunk 1 / 2" in content
    assert expected_chunk_calls[0][0] in content
    assert expected_chunk_calls[0][1] in content
    assert "応答1" in content
    assert "## Merge request" in content
    assert expected_merge_call[1] in content
    assert "応答3" in content


def test_analysis_export_is_unavailable_before_chunks_are_prepared():
    service = MemoryJobService()
    job = MemoryJobState(
        job_id="pending-job",
        total=1,
        regenerate_existing=False,
        language="ja",
    )
    service._jobs[job.job_id] = job

    assert service.get_job_analysis_export(job.job_id) is None


def test_download_analysis_endpoint_returns_markdown(monkeypatch):
    app = FastAPI()
    app.include_router(memory_router.router, prefix="/api")
    monkeypatch.setattr(
        memory_router.memory_job_service,
        "get_job_status",
        lambda job_id: {"job_id": job_id},
    )
    monkeypatch.setattr(
        memory_router.memory_job_service,
        "get_job_analysis_export",
        lambda job_id: ("# Analysis\n", "memory-analysis-test.md"),
    )

    with TestClient(app) as client:
        response = client.get("/api/memory/generate/export/test-job")

    assert response.status_code == 200
    assert response.text == "# Analysis\n"
    assert response.headers["content-type"].startswith("text/markdown")
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="memory-analysis-test.md"'
    )
