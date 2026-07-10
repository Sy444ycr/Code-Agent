# Code Agent

Course project for AI4SE Project A: Coding Agent Harness.

This repository will contain a small, self-implemented coding agent harness. The planned direction is a CLI-first harness with deterministic mock-LLM tests, code-level guardrails, tool dispatch, feedback loops, memory, configuration, and distribution support.

## Project Status

Current phase: repository setup and specification.

Implementation code will be added only after the Superpowers brainstorming and planning workflow produces approved `SPEC.md` and `PLAN.md`.

## Required Workflow

1. Brainstorm and approve the design.
2. Write `SPEC.md`.
3. Write `PLAN.md`.
4. Cold-start validate the spec and plan with a fresh agent.
5. Implement tasks with TDD.
6. Review, document, package, and distribute.

## Security Boundary

Do not commit real API keys, credentials, tokens, or local secrets.

Use `.env.example` as documentation only. Real `.env` files are ignored by Git.

## Repository Layout

```text
.
|-- README.md
|-- SPEC.md
|-- PLAN.md
|-- SPEC_PROCESS.md
|-- AGENT_LOG.md
|-- REFLECTION.md
|-- docs/
|   `-- superpowers/
|       `-- specs/
|-- .env.example
|-- .gitignore
|-- AI4SE_Final_Project_A_Coding_Agent_Harness.md
`-- AI4SE_通用要求.md
```

## Development

Development commands will be documented after the technical stack is finalized in `SPEC.md`.
