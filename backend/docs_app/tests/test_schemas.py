"""
Schema 邊界與錯誤訊息測試

- Delta 操作的最小合法值與錯誤訊息（訊息會經 WebSocket 錯誤回傳給前端顯示）
- LLM 結構化輸出（ProofreadResult / DocumentMetadata）的範圍限制：
  pydantic-ai 依這些限制驗證模型輸出並要求重試，放寬會讓不合理的值流到前端
- 請求 Schema 的預設值
"""

import pytest
from pydantic import ValidationError

from docs_app.schemas import (
    AIAskStreamMessage,
    CommentCreateSchema,
    CommentUpdateSchema,
    CursorMoveMessage,
    DeltaOperationSchema,
    DocumentMetadata,
    ProofreadResult,
    ShareRequestSchema,
    WritingIssue,
)


def error_messages(excinfo):
    return [err['msg'] for err in excinfo.value.errors()]


class TestDeltaOperationBoundaries:

    @pytest.mark.parametrize('field', ['retain', 'delete'])
    def test_one_is_the_smallest_valid_length(self, field):
        op = DeltaOperationSchema(**{field: 1})
        assert getattr(op, field) == 1

    @pytest.mark.parametrize('field', ['retain', 'delete'])
    def test_zero_rejected_with_message(self, field):
        with pytest.raises(ValidationError) as excinfo:
            DeltaOperationSchema(**{field: 0})
        assert error_messages(excinfo) == [f'Value error, {field} must be a positive integer']

    def test_multiple_operation_types_rejected_with_message(self):
        with pytest.raises(ValidationError) as excinfo:
            DeltaOperationSchema(insert='a', retain=1)
        assert error_messages(excinfo) == [
            'Value error, Each delta operation must have exactly one of: insert, retain, or delete'
        ]


class TestCommentContentMessages:

    @pytest.mark.parametrize('schema', [CommentCreateSchema, CommentUpdateSchema])
    @pytest.mark.parametrize('content', ['', '   '])
    def test_blank_content_message(self, schema, content):
        with pytest.raises(ValidationError) as excinfo:
            schema(content=content)
        assert error_messages(excinfo) == ['Value error, 評論內容不能為空']

    @pytest.mark.parametrize('schema', [CommentCreateSchema, CommentUpdateSchema])
    def test_too_long_message(self, schema):
        with pytest.raises(ValidationError) as excinfo:
            schema(content='x' * 5001)
        assert error_messages(excinfo) == ['Value error, 評論內容不能超過 5000 字元']


class TestLLMOutputConstraints:

    @pytest.mark.parametrize('score', [0, 100])
    def test_score_bounds_accepted(self, score):
        assert ProofreadResult(issues=[], overall_score=score).overall_score == score

    @pytest.mark.parametrize('score', [-1, 101])
    def test_score_out_of_range_rejected(self, score):
        with pytest.raises(ValidationError):
            ProofreadResult(issues=[], overall_score=score)

    @pytest.mark.parametrize('severity', ['info', 'warning', 'error'])
    def test_known_severities_accepted(self, severity):
        issue = WritingIssue(original='a', suggestion='b', reason='c', severity=severity)
        assert issue.severity == severity

    def test_unknown_severity_rejected(self):
        with pytest.raises(ValidationError):
            WritingIssue(original='a', suggestion='b', reason='c', severity='critical')

    def test_reading_time_cannot_be_negative(self):
        assert DocumentMetadata(summary='s', tags=[], language='en', reading_time=0).reading_time == 0
        with pytest.raises(ValidationError):
            DocumentMetadata(summary='s', tags=[], language='en', reading_time=-1)


class TestRequestDefaults:

    def test_cursor_length_defaults_to_zero(self):
        assert CursorMoveMessage(index=3).length == 0

    def test_ask_document_text_defaults_to_empty(self):
        assert AIAskStreamMessage(question='q').document_text == ''

    def test_share_defaults_to_write_permission(self):
        assert ShareRequestSchema(username='bob').permission == 'write'
