"""
Tests for IntentOS Typed Handoff Schemas (Phase 2B.2).
Pydantic models enforcing type safety on agent-to-agent communication.
"""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from core.orchestration.schemas import (
    FileInfo,
    FileListResult,
    WebResult,
    SearchResult,
    DocumentResult,
    SubTask,
    IntentObject,
    ErrorDetail,
    TaskMetadata,
    SubtaskResult,
    AgentOutput,
    CostRecord,
    ExecutionContext,
)


# ---------------------------------------------------------------------------
# FileInfo (tests 1-3)
# ---------------------------------------------------------------------------

class TestFileInfo:
    def test_create_file_info(self):
        """Test 1: Create FileInfo with all required fields."""
        now = datetime.now(timezone.utc)
        fi = FileInfo(
            path="/workspace/readme.md",
            name="readme.md",
            size_bytes=1024,
            modified=now,
            file_type="markdown",
        )
        assert fi.path == "/workspace/readme.md"
        assert fi.name == "readme.md"
        assert fi.size_bytes == 1024
        assert fi.modified == now
        assert fi.file_type == "markdown"

    def test_file_info_serialization_roundtrip(self):
        """Test 2: FileInfo serializes to dict and back."""
        now = datetime.now(timezone.utc)
        fi = FileInfo(
            path="/a/b.txt",
            name="b.txt",
            size_bytes=42,
            modified=now,
            file_type="text",
        )
        data = fi.model_dump()
        restored = FileInfo.model_validate(data)
        assert restored == fi

    def test_file_info_from_raw_dict(self):
        """Test 3: FileInfo from a raw dict (e.g. agent output)."""
        raw = {
            "path": "/tmp/out.csv",
            "name": "out.csv",
            "size_bytes": 999,
            "modified": "2026-01-15T10:30:00+00:00",
            "file_type": "csv",
        }
        fi = FileInfo.model_validate(raw)
        assert fi.name == "out.csv"
        assert fi.size_bytes == 999
        assert isinstance(fi.modified, datetime)


# ---------------------------------------------------------------------------
# FileListResult (tests 4-5)
# ---------------------------------------------------------------------------

class TestFileListResult:
    def test_file_list_result_fields(self):
        """Test 4: FileListResult contains files, total_count, total_size_bytes."""
        now = datetime.now(timezone.utc)
        files = [
            FileInfo(path="/a.txt", name="a.txt", size_bytes=10, modified=now, file_type="text"),
            FileInfo(path="/b.txt", name="b.txt", size_bytes=20, modified=now, file_type="text"),
        ]
        flr = FileListResult(files=files, total_count=2, total_size_bytes=30)
        assert flr.total_count == 2
        assert flr.total_size_bytes == 30
        assert len(flr.files) == 2

    def test_total_count_must_match_len_files(self):
        """Test 5: total_count must match len(files)."""
        now = datetime.now(timezone.utc)
        files = [
            FileInfo(path="/a.txt", name="a.txt", size_bytes=10, modified=now, file_type="text"),
        ]
        with pytest.raises(ValidationError):
            FileListResult(files=files, total_count=99, total_size_bytes=10)


# ---------------------------------------------------------------------------
# SearchResult / WebResult (test 6-7)
# ---------------------------------------------------------------------------

class TestSearchResult:
    def test_search_result_fields(self):
        """Test 6: SearchResult contains query, results, total_results."""
        wr = WebResult(url="https://example.com", title="Example", snippet="A snippet")
        sr = SearchResult(query="test query", results=[wr], total_results=1)
        assert sr.query == "test query"
        assert sr.total_results == 1
        assert sr.results[0].url == "https://example.com"

    def test_web_result_fields(self):
        """Test 7: WebResult has url, title, snippet."""
        wr = WebResult(url="https://x.com", title="X", snippet="snip")
        assert wr.url == "https://x.com"
        assert wr.title == "X"
        assert wr.snippet == "snip"


# ---------------------------------------------------------------------------
# DocumentResult (test 8)
# ---------------------------------------------------------------------------

class TestDocumentResult:
    def test_document_result_fields(self):
        """Test 8: DocumentResult with optional content and page_count."""
        dr = DocumentResult(path="/doc.pdf", format="pdf", content=None, page_count=12)
        assert dr.path == "/doc.pdf"
        assert dr.format == "pdf"
        assert dr.content is None
        assert dr.page_count == 12

    def test_document_result_with_content(self):
        dr = DocumentResult(path="/doc.txt", format="text", content="hello world")
        assert dr.content == "hello world"
        assert dr.page_count is None


# ---------------------------------------------------------------------------
# IntentObject / SubTask (tests 9-11)
# ---------------------------------------------------------------------------

class TestIntentObject:
    def test_intent_object_fields(self):
        """Test 9: IntentObject contains raw_input, intent, subtasks."""
        st = SubTask(id="st-1", agent="file_agent", action="list", params={"dir": "/tmp"})
        io = IntentObject(raw_input="list files", intent="file_list", subtasks=[st])
        assert io.raw_input == "list files"
        assert io.intent == "file_list"
        assert len(io.subtasks) == 1

    def test_subtask_fields(self):
        """Test 10: SubTask has id, agent, action, params."""
        st = SubTask(id="st-2", agent="web_agent", action="search", params={"q": "hello"})
        assert st.id == "st-2"
        assert st.agent == "web_agent"
        assert st.action == "search"
        assert st.params == {"q": "hello"}

    def test_intent_object_roundtrip(self):
        """Test 11: Full IntentObject serialization round-trip."""
        st = SubTask(id="st-1", agent="file_agent", action="read", params={"path": "/x"})
        io = IntentObject(raw_input="read x", intent="file_read", subtasks=[st])
        data = io.model_dump()
        restored = IntentObject.model_validate(data)
        assert restored == io
        assert restored.subtasks[0].params == {"path": "/x"}


# ---------------------------------------------------------------------------
# SubtaskResult / ErrorDetail / TaskMetadata (tests 12-15)
# ---------------------------------------------------------------------------

class TestSubtaskResult:
    def test_subtask_result_fields(self):
        """Test 12: SubtaskResult basic fields and status values."""
        meta = TaskMetadata(files_affected=1, bytes_affected=100, duration_ms=50, paths_accessed=["/a"])
        sr = SubtaskResult(
            subtask_id="st-1",
            agent="file_agent",
            action="list",
            status="success",
            result={"count": 5},
            error=None,
            metadata=meta,
        )
        assert sr.status == "success"
        assert sr.result == {"count": 5}

    def test_subtask_result_with_error(self):
        """Test 13: SubtaskResult with error status and ErrorDetail."""
        err = ErrorDetail(code="NOT_FOUND", message="File not found")
        meta = TaskMetadata(files_affected=0, bytes_affected=0, duration_ms=10, paths_accessed=[])
        sr = SubtaskResult(
            subtask_id="st-2",
            agent="file_agent",
            action="read",
            status="error",
            result=None,
            error=err,
            metadata=meta,
        )
        assert sr.error.code == "NOT_FOUND"

    def test_error_detail_fields(self):
        """Test 14: ErrorDetail has code and message."""
        ed = ErrorDetail(code="PERM_DENIED", message="No access")
        assert ed.code == "PERM_DENIED"
        assert ed.message == "No access"

    def test_task_metadata_fields(self):
        """Test 15: TaskMetadata fields."""
        tm = TaskMetadata(
            files_affected=3,
            bytes_affected=2048,
            duration_ms=120,
            paths_accessed=["/a", "/b"],
        )
        assert tm.files_affected == 3
        assert tm.bytes_affected == 2048
        assert tm.duration_ms == 120
        assert tm.paths_accessed == ["/a", "/b"]

    def test_subtask_result_status_values(self):
        """Status must be one of success/error/confirmation_required."""
        meta = TaskMetadata(files_affected=0, bytes_affected=0, duration_ms=0, paths_accessed=[])
        with pytest.raises(ValidationError):
            SubtaskResult(
                subtask_id="st-x",
                agent="a",
                action="b",
                status="invalid_status",
                result=None,
                error=None,
                metadata=meta,
            )


# ---------------------------------------------------------------------------
# AgentOutput (tests 16-18)
# ---------------------------------------------------------------------------

class TestAgentOutput:
    def test_agent_output_success(self):
        """Test 16: Standard agent output model."""
        ao = AgentOutput(
            status="success",
            action_performed="file_list",
            result={"files": []},
            metadata={"duration": 100},
        )
        assert ao.status == "success"
        assert ao.action_performed == "file_list"
        assert ao.confirmation_prompt is None
        assert ao.error is None

    def test_agent_output_error_requires_error_field(self):
        """Test 17: If status=='error', error field must be present."""
        with pytest.raises(ValidationError):
            AgentOutput(
                status="error",
                action_performed="file_read",
                result=None,
                metadata={},
            )

    def test_agent_output_confirmation_requires_prompt(self):
        """Test 18: If status=='confirmation_required', confirmation_prompt must be present."""
        with pytest.raises(ValidationError):
            AgentOutput(
                status="confirmation_required",
                action_performed="file_delete",
                result=None,
                metadata={},
            )

    def test_agent_output_error_valid(self):
        """Error status with error field should work."""
        err = ErrorDetail(code="FAIL", message="something broke")
        ao = AgentOutput(
            status="error",
            action_performed="file_read",
            result=None,
            error=err,
            metadata={},
        )
        assert ao.error.code == "FAIL"

    def test_agent_output_confirmation_valid(self):
        """Confirmation status with prompt should work."""
        ao = AgentOutput(
            status="confirmation_required",
            action_performed="file_delete",
            result=None,
            confirmation_prompt="Delete /tmp/x?",
            metadata={},
        )
        assert ao.confirmation_prompt == "Delete /tmp/x?"


# ---------------------------------------------------------------------------
# CostRecord (test 19)
# ---------------------------------------------------------------------------

class TestCostRecord:
    def test_cost_record_fields(self):
        """Test 19: CostRecord fields."""
        now = datetime.now(timezone.utc)
        cr = CostRecord(
            model="gpt-4",
            input_tokens=500,
            output_tokens=200,
            cost_usd=0.03,
            task_id="task-abc",
            timestamp=now,
        )
        assert cr.model == "gpt-4"
        assert cr.input_tokens == 500
        assert cr.output_tokens == 200
        assert cr.cost_usd == 0.03
        assert cr.task_id == "task-abc"
        assert cr.timestamp == now


# ---------------------------------------------------------------------------
# ExecutionContext (test 20)
# ---------------------------------------------------------------------------

class TestExecutionContext:
    def test_execution_context_fields(self):
        """Test 20: ExecutionContext fields."""
        ec = ExecutionContext(
            user="alice",
            workspace="/home/alice/project",
            granted_paths=["/home/alice/project", "/tmp"],
            task_id="task-xyz",
            dry_run=True,
        )
        assert ec.user == "alice"
        assert ec.workspace == "/home/alice/project"
        assert ec.granted_paths == ["/home/alice/project", "/tmp"]
        assert ec.task_id == "task-xyz"
        assert ec.dry_run is True


# ---------------------------------------------------------------------------
# Cross-schema integration (tests 21-22)
# ---------------------------------------------------------------------------

class TestCrossSchemaIntegration:
    def test_subtask_result_holds_file_list_result(self):
        """Test 21: SubtaskResult can hold a FileListResult as its result field."""
        now = datetime.now(timezone.utc)
        files = [
            FileInfo(path="/a.txt", name="a.txt", size_bytes=10, modified=now, file_type="text"),
        ]
        flr = FileListResult(files=files, total_count=1, total_size_bytes=10)
        meta = TaskMetadata(files_affected=1, bytes_affected=10, duration_ms=5, paths_accessed=["/a.txt"])
        sr = SubtaskResult(
            subtask_id="st-1",
            agent="file_agent",
            action="list",
            status="success",
            result=flr.model_dump(),
            error=None,
            metadata=meta,
        )
        # Verify we can reconstruct FileListResult from the result field
        reconstructed = FileListResult.model_validate(sr.result)
        assert reconstructed.total_count == 1
        assert reconstructed.files[0].name == "a.txt"

    def test_agent_output_from_agent_dict(self):
        """Test 22: AgentOutput can be constructed from existing agent dict outputs."""
        raw = {
            "status": "success",
            "action": "file_list",
            "result": {"files": ["/a.txt"]},
            "metadata": {"duration": 50},
        }
        ao = AgentOutput.from_agent_output(raw)
        assert ao.status == "success"
        assert ao.action_performed == "file_list"
        assert ao.result == {"files": ["/a.txt"]}

    def test_agent_output_from_agent_dict_error(self):
        """from_agent_output handles error dicts."""
        raw = {
            "status": "error",
            "action": "file_read",
            "error": "File not found",
            "metadata": {},
        }
        ao = AgentOutput.from_agent_output(raw)
        assert ao.status == "error"
        assert ao.error is not None
        assert ao.error.message == "File not found"
