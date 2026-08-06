from code_agent.core.context import ContextBuilder
from code_agent.core.memory import InMemoryMemoryStore, MemoryEntry
from code_agent.core.models import FeedbackSignal, FeedbackStatus, LoopSpec, Task


def test_unverified_memory_is_not_promoted() -> None:
    store = InMemoryMemoryStore()
    entry = store.add_candidate(
        MemoryEntry(
            workspace="/repo", type="rule", tags=["python"], content="Use pytest", evidence=[]
        )
    )
    assert entry.verified_at is None
    assert store.search("/repo", ["python"], limit=5) == []


def test_verified_memory_enters_context() -> None:
    store = InMemoryMemoryStore()
    store.add_verified(
        MemoryEntry(
            workspace="/repo",
            type="rule",
            tags=["python"],
            content="Use pytest",
            evidence=["user confirmed"],
        )
    )
    context = ContextBuilder(store, max_chars=800).build(
        Task(workspace="/repo", goal="fix tests"),
        LoopSpec(goal="fix tests", acceptance_checks=["pytest -q"]),
        feedback=[],
    )
    assert "Use pytest" in context
    assert "pytest -q" in context


def test_context_redacts_known_secret_patterns() -> None:
    signal = FeedbackSignal(
        source="shell",
        status=FeedbackStatus.FAILED,
        summary="OPENAI_API_KEY=sk-secret123",
        evidence=[],
    )
    context = ContextBuilder(InMemoryMemoryStore(), max_chars=800).build(
        Task(workspace="/repo", goal="fix"), LoopSpec(goal="fix"), feedback=[signal]
    )
    assert "sk-secret123" not in context
    assert "[REDACTED]" in context
