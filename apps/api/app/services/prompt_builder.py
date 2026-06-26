"""Prompt builder — assembles the full agent prompt for a run.

Includes: persona role, ticket packet (title/description/AC), digestible comments,
selected skills/plugins, the required output path + output contract, author/run id,
and the review comment when this is a rerun.
"""
from __future__ import annotations

from ..models import Ticket


def output_contract_text(run_id: int, ticket, agent: str, model: str, persona: str, output_path: str) -> str:
    return (
        "## Output contract (REQUIRED)\n"
        f"- Write all deliverables under: `{output_path}`\n"
        "- When finished, write a sentinel file `.agent_done.json` in that directory containing:\n"
        "  ```json\n"
        "  {\n"
        f'    "run_id": {run_id}, "ticket_id": {ticket.id}, "ticket_number": "{ticket.ticket_number}",\n'
        f'    "agent": "{agent}", "model": "{model}", "persona": "{persona}",\n'
        '    "status": "success",  // or "failed"\n'
        '    "summary": "one-line summary of what you produced",\n'
        '    "artifacts": ["<absolute path>", "..."],\n'
        f'    "author_name": "{persona}", "finished_at": "<ISO-8601>"\n'
        "  }\n"
        "  ```\n"
        "- Do NOT write outside the assigned output path (workspace allowlist).\n"
        "- Do NOT include secrets/tokens; reference them by name only.\n"
    )


def build_prompt(
    ticket: Ticket,
    *,
    run_id: int,
    run_number: int,
    persona: str,
    agent: str,
    model: str,
    skills: list[str],
    output_path: str,
    review_comment: str | None = None,
    previous_output_path: str | None = None,
) -> str:
    digestible = [c for c in ticket.comments if c.is_digestible]
    comment_block = "\n".join(
        f"- ({c.author_type}) {c.author_name or ''}: {c.body_md}" for c in digestible
    ) or "_No comments._"

    skill_block = "\n".join(f"- {s}" for s in skills) or "_None selected._"

    sections = [
        f"# Agent task — {ticket.ticket_number} (run #{run_number})",
        "",
        f"You are acting as the **{persona}** persona, executing on **{agent}** ({model}).",
        "",
        "## Ticket",
        f"**Title:** {ticket.title}",
        "",
        "**Description:**",
        ticket.description_md or "_No description._",
        "",
        "## Acceptance Criteria",
        ticket.acceptance_criteria_md or "_None specified._",
        "",
        "## Relevant comments",
        comment_block,
        "",
        "## Selected skills / plugins",
        skill_block,
        "",
        output_contract_text(run_id, ticket, agent, model, persona, output_path),
    ]

    if review_comment:
        rerun = [
            "",
            "## RERUN — address this review feedback",
            f"The previous attempt was NOT accepted. Reviewer (Kay) said:\n\n> {review_comment}",
        ]
        if previous_output_path:
            rerun.append(f"\nPrevious output is at `{previous_output_path}`. Improve on it; do not repeat the same mistakes.")
        sections.extend(rerun)

    return "\n".join(sections) + "\n"
