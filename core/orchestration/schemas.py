"""
IntentOS Typed Handoff Schemas (Phase 2B.2).

Pydantic models enforcing type safety on all agent-to-agent communication.
Inspired by MetaGPT's ActionNode typed outputs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, model_validator


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

class FileInfo(BaseModel):
    """Metadata about a single file."""
    path: str
    name: str
    size_bytes: int
    modified: datetime
    file_type: str


class FileListResult(BaseModel):
    """Result of a file-listing operation."""
    files: List[FileInfo]
    total_count: int
    total_size_bytes: int

    @model_validator(mode="after")
    def _check_total_count(self) -> "FileListResult":
        if self.total_count != len(self.files):
            raise ValueError(
                f"total_count ({self.total_count}) must match len(files) ({len(self.files)})"
            )
        return self


class WebResult(BaseModel):
    """A single web search result."""
    url: str
    title: str
    snippet: str


class SearchResult(BaseModel):
    """Result of a web search."""
    query: str
    results: List[WebResult]
    total_results: int


class DocumentResult(BaseModel):
    """Result of a document read/parse operation."""
    path: str
    format: str
    content: Optional[str] = None
    page_count: Optional[int] = None


# ---------------------------------------------------------------------------
# Intent / SubTask
# ---------------------------------------------------------------------------

class SubTask(BaseModel):
    """A single subtask within an intent decomposition."""
    id: str
    agent: str
    action: str
    params: Dict[str, Any]


class IntentObject(BaseModel):
    """Decomposed user intent with subtasks."""
    raw_input: str
    intent: str
    subtasks: List[SubTask]


# ---------------------------------------------------------------------------
# Error / Metadata helpers
# ---------------------------------------------------------------------------

class ErrorDetail(BaseModel):
    """Structured error information."""
    code: str
    message: str


class TaskMetadata(BaseModel):
    """Metadata about a completed task."""
    files_affected: int
    bytes_affected: int
    duration_ms: int
    paths_accessed: List[str]


# ---------------------------------------------------------------------------
# SubtaskResult
# ---------------------------------------------------------------------------

_VALID_SUBTASK_STATUSES = {"success", "error", "confirmation_required"}


class SubtaskResult(BaseModel):
    """Result of executing a single subtask."""
    subtask_id: str
    agent: str
    action: str
    status: str
    result: Any = None
    error: Optional[ErrorDetail] = None
    metadata: TaskMetadata

    @model_validator(mode="after")
    def _validate_status(self) -> "SubtaskResult":
        if self.status not in _VALID_SUBTASK_STATUSES:
            raise ValueError(
                f"status must be one of {_VALID_SUBTASK_STATUSES}, got '{self.status}'"
            )
        return self


# ---------------------------------------------------------------------------
# AgentOutput
# ---------------------------------------------------------------------------

class AgentOutput(BaseModel):
    """Standard agent output model with cross-cutting validations."""
    status: str
    action_performed: str
    result: Any = None
    confirmation_prompt: Optional[str] = None
    error: Optional[ErrorDetail] = None
    metadata: Any = None

    @model_validator(mode="after")
    def _validate_conditionals(self) -> "AgentOutput":
        if self.status == "error" and self.error is None:
            raise ValueError("error field is required when status is 'error'")
        if self.status == "confirmation_required" and self.confirmation_prompt is None:
            raise ValueError(
                "confirmation_prompt is required when status is 'confirmation_required'"
            )
        return self

    @classmethod
    def from_agent_output(cls, raw: Dict[str, Any]) -> "AgentOutput":
        """Construct an AgentOutput from the dict format current agents return.

        Handles common key differences:
        - 'action' -> 'action_performed'
        - 'error' as plain string -> ErrorDetail
        """
        error = raw.get("error")
        error_detail: Optional[ErrorDetail] = None
        if error is not None:
            if isinstance(error, str):
                error_detail = ErrorDetail(code="AGENT_ERROR", message=error)
            elif isinstance(error, dict):
                error_detail = ErrorDetail.model_validate(error)
            elif isinstance(error, ErrorDetail):
                error_detail = error

        return cls(
            status=raw.get("status", "success"),
            action_performed=raw.get("action_performed") or raw.get("action", "unknown"),
            result=raw.get("result"),
            confirmation_prompt=raw.get("confirmation_prompt"),
            error=error_detail,
            metadata=raw.get("metadata"),
        )


# ---------------------------------------------------------------------------
# CostRecord
# ---------------------------------------------------------------------------

class CostRecord(BaseModel):
    """Tracks token usage and cost for a single LLM call."""
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    task_id: str
    timestamp: datetime


# ---------------------------------------------------------------------------
# ExecutionContext
# ---------------------------------------------------------------------------

class ExecutionContext(BaseModel):
    """Security and runtime context for task execution."""
    user: str
    workspace: str
    granted_paths: List[str]
    task_id: str
    dry_run: bool = False
