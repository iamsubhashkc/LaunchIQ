from __future__ import annotations

from .models import ClarificationPrompt, QueryPlan


AMBIGUOUS_TERMS: dict[str, ClarificationPrompt] = {
    "impact": ClarificationPrompt(
        question="What deterministic output should LaunchIQ return for impact: a list, a count, or a grouped distribution?",
        field="intent",
        options=["list", "count", "distribution"],
        reason="The word 'impact' is qualitative unless we map it to a concrete aggregation.",
    ),
    "mitigation plan": ClarificationPrompt(
        question="Should LaunchIQ return the impacted vehicle list only, or should it also include the underlying readiness fields for manual mitigation planning?",
        field="requested_columns",
        options=["list_only", "list_with_readiness_fields"],
        reason="Mitigation planning is not stored as a deterministic field in the dataset.",
    ),
    "peak load": ClarificationPrompt(
        question="Should peak load be grouped month-wise only, or month-wise by platform as well?",
        field="group_by",
        options=["month", "month_and_platform"],
        reason="Peak load can refer to volume by month or concentration by month and platform.",
    ),
    "lagging": ClarificationPrompt(
        question="How should LaunchIQ define lagging: missing capability entirely or below a specific readiness threshold?",
        field="lag_definition",
        options=["missing_capability", "below_threshold"],
        reason="Lagging needs an explicit deterministic rule.",
    ),
}


def merge_clarification_answers(query: str, answers: dict[str, str]) -> str:
    if not answers:
        return query
    fragments = [query.strip(), "Clarification answers:"]
    for key, value in answers.items():
        fragments.append(f"- {key}: {value}")
    return "\n".join(fragments)


def detect_clarifications(plan: QueryPlan, query: str) -> QueryPlan:
    lowered = query.lower()
    prompts = list(plan.clarification_questions)

    for trigger, prompt in AMBIGUOUS_TERMS.items():
        if trigger == "impact" and "volume impact" in lowered:
            continue
        if trigger in lowered and prompt.field not in {item.field for item in prompts}:
            prompts.append(prompt)
            plan.ambiguity_notes.append(prompt.reason)

    if plan.intent == "distribution" and not plan.group_by:
        prompts.append(
            ClarificationPrompt(
                question="Which dimension should LaunchIQ use for the distribution?",
                field="group_by",
                options=["region_scope", "platform", "architecture", "tcu_generation"],
                reason="Distribution queries need an explicit grouping dimension.",
            )
        )
        plan.ambiguity_notes.append("Distribution requested without a grouping dimension.")

    plan.clarification_questions = prompts
    return plan
