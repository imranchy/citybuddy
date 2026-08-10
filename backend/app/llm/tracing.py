from contextlib import contextmanager
from dataclasses import dataclass
import importlib
import os
from typing import Any, Iterator


class LangSmithConfigurationError(RuntimeError):
    """Raised when explicitly requested tracing cannot be configured."""


@dataclass(frozen=True, slots=True)
class TraceConfig:
    enabled: bool = False
    project: str = "citybuddy-local-evaluation"

    @classmethod
    def from_environment(
        cls,
        *,
        enabled: bool = False,
        project: str | None = None,
    ) -> "TraceConfig":
        selected_project = project or os.getenv(
            "LANGSMITH_PROJECT", "citybuddy-local-evaluation"
        )
        if enabled and not os.getenv("LANGSMITH_API_KEY"):
            raise LangSmithConfigurationError(
                "--langsmith requires LANGSMITH_API_KEY. Tracing remains opt-in."
            )
        return cls(enabled=enabled, project=selected_project)


@contextmanager
def trace_evaluation_case(
    config: TraceConfig,
    *,
    name: str,
    inputs: dict[str, Any],
    metadata: dict[str, Any],
) -> Iterator[Any | None]:
    """Create one LangSmith trace only when the caller explicitly opts in."""

    if not config.enabled:
        yield None
        return

    try:
        langsmith = importlib.import_module("langsmith")
    except ImportError as error:
        raise LangSmithConfigurationError(
            "Install backend requirements before using --langsmith."
        ) from error

    with langsmith.tracing_context(enabled=True, project_name=config.project):
        with langsmith.trace(
            name,
            run_type="chain",
            inputs=inputs,
            metadata=metadata,
            tags=["citybuddy", "offline-evaluation"],
        ) as run:
            yield run


def finish_trace(run: Any | None, *, outputs: dict[str, Any] | None = None) -> None:
    if run is None:
        return
    run.end(outputs=outputs or {})
