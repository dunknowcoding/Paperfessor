from __future__ import annotations

from src.prompting import compose_system_prompt


def test_compose_system_prompt_includes_guardrails_and_shared_skills() -> None:
    text = compose_system_prompt("phd", "You are the planner.")

    assert "You are the planner." in text
    assert "Operating guardrails" in text
    assert "Windows Credential Manager" in text
    assert "Shared operating skills" in text
    assert "Prompt engineering foundation" in text
    assert "Stage handoff and communication protocol" in text


def test_compose_system_prompt_respects_role_write_scope() -> None:
    ug_text = compose_system_prompt("ug", "Implement the task.")
    ms_text = compose_system_prompt("ms", "Survey the literature.")
    ug_scope = ug_text.split("Your allowed write scope for this role is:\n", 1)[1].split(
        "\n\nBefore handing work", 1
    )[0]
    ms_scope = ms_text.split("Your allowed write scope for this role is:\n", 1)[1].split(
        "\n\nBefore handing work", 1
    )[0]

    assert "workspace/src/" in ug_scope
    assert "workspace/shared/code_log.md" in ug_scope
    assert "workspace/shared/research_log.md" in ms_scope
    assert "workspace/src/" not in ms_scope


def test_compose_system_prompt_can_skip_skills_block() -> None:
    text = compose_system_prompt("phd", "System only.", with_skills=False)

    assert "System only." in text
    assert "Operating guardrails" in text
    assert "Prompt engineering foundation" not in text