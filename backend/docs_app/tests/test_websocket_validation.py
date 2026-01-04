"""
WebSocket 消息驗證測試模組

測試 Delta Schema 驗證和 WebSocket 消息格式驗證
"""

import json

import pytest
from pydantic import ValidationError
from docs_app.schemas import (
    DeltaOperationSchema,
    DeltaSchema,
    WebSocketMessageSchema
)


class TestDeltaOperationSchema:
    """Delta 操作 Schema 測試"""

    def test_valid_insert_text(self):
        """測試有效的文字插入操作"""
        op = DeltaOperationSchema(insert="Hello")
        assert op.insert == "Hello"
        assert op.retain is None
        assert op.delete is None

    def test_valid_insert_with_attributes(self):
        """測試帶屬性的插入操作"""
        op = DeltaOperationSchema(
            insert="Bold text",
            attributes={"bold": True}
        )
        assert op.insert == "Bold text"
        assert op.attributes == {"bold": True}

    def test_valid_insert_embed(self):
        """測試嵌入對象插入（如圖片）"""
        op = DeltaOperationSchema(
            insert={"image": "https://example.com/image.png"}
        )
        assert op.insert == {"image": "https://example.com/image.png"}

    def test_valid_insert_newline(self):
        """測試換行符插入"""
        op = DeltaOperationSchema(insert="\n")
        assert op.insert == "\n"

    def test_valid_retain(self):
        """測試有效的保留操作"""
        op = DeltaOperationSchema(retain=5)
        assert op.retain == 5

    def test_valid_retain_with_attributes(self):
        """測試帶屬性的保留操作（格式化）"""
        op = DeltaOperationSchema(
            retain=10,
            attributes={"bold": True, "italic": True}
        )
        assert op.retain == 10
        assert op.attributes == {"bold": True, "italic": True}

    def test_valid_delete(self):
        """測試有效的刪除操作"""
        op = DeltaOperationSchema(delete=3)
        assert op.delete == 3

    def test_invalid_no_operation(self):
        """測試缺少操作類型時應拋出錯誤"""
        with pytest.raises(ValidationError) as exc_info:
            DeltaOperationSchema()
        assert "exactly one of" in str(exc_info.value).lower()

    def test_invalid_multiple_operations_insert_retain(self):
        """測試同時有 insert 和 retain 時應拋出錯誤"""
        with pytest.raises(ValidationError) as exc_info:
            DeltaOperationSchema(insert="text", retain=5)
        assert "exactly one of" in str(exc_info.value).lower()

    def test_invalid_multiple_operations_insert_delete(self):
        """測試同時有 insert 和 delete 時應拋出錯誤"""
        with pytest.raises(ValidationError) as exc_info:
            DeltaOperationSchema(insert="text", delete=3)
        assert "exactly one of" in str(exc_info.value).lower()

    def test_invalid_multiple_operations_retain_delete(self):
        """測試同時有 retain 和 delete 時應拋出錯誤"""
        with pytest.raises(ValidationError) as exc_info:
            DeltaOperationSchema(retain=5, delete=3)
        assert "exactly one of" in str(exc_info.value).lower()

    def test_invalid_all_operations(self):
        """測試同時有三個操作類型時應拋出錯誤"""
        with pytest.raises(ValidationError) as exc_info:
            DeltaOperationSchema(insert="text", retain=5, delete=3)
        assert "exactly one of" in str(exc_info.value).lower()

    def test_invalid_retain_zero(self):
        """測試 retain 為 0 時應拋出錯誤"""
        with pytest.raises(ValidationError) as exc_info:
            DeltaOperationSchema(retain=0)
        assert "positive integer" in str(exc_info.value).lower()

    def test_invalid_retain_negative(self):
        """測試 retain 為負數時應拋出錯誤"""
        with pytest.raises(ValidationError) as exc_info:
            DeltaOperationSchema(retain=-1)
        assert "positive integer" in str(exc_info.value).lower()

    def test_invalid_delete_zero(self):
        """測試 delete 為 0 時應拋出錯誤"""
        with pytest.raises(ValidationError) as exc_info:
            DeltaOperationSchema(delete=0)
        assert "positive integer" in str(exc_info.value).lower()

    def test_invalid_delete_negative(self):
        """測試 delete 為負數時應拋出錯誤"""
        with pytest.raises(ValidationError) as exc_info:
            DeltaOperationSchema(delete=-1)
        assert "positive integer" in str(exc_info.value).lower()


class TestDeltaSchema:
    """Delta Schema 測試"""

    def test_valid_delta_single_insert(self):
        """測試單個插入操作的有效 Delta"""
        delta = DeltaSchema(ops=[{"insert": "Hello"}])
        assert len(delta.ops) == 1
        assert delta.ops[0].insert == "Hello"

    def test_valid_delta_multiple_operations(self):
        """測試多個操作的有效 Delta"""
        delta = DeltaSchema(ops=[
            {"insert": "Hello "},
            {"insert": "World", "attributes": {"bold": True}},
            {"insert": "\n"}
        ])
        assert len(delta.ops) == 3

    def test_valid_delta_mixed_operations(self):
        """測試混合操作類型的 Delta"""
        delta = DeltaSchema(ops=[
            {"retain": 5},
            {"delete": 3},
            {"insert": "new text"}
        ])
        assert len(delta.ops) == 3
        assert delta.ops[0].retain == 5
        assert delta.ops[1].delete == 3
        assert delta.ops[2].insert == "new text"

    def test_invalid_empty_ops(self):
        """測試空的 ops 陣列應拋出錯誤"""
        with pytest.raises(ValidationError) as exc_info:
            DeltaSchema(ops=[])
        assert "cannot be empty" in str(exc_info.value).lower()

    def test_invalid_missing_ops(self):
        """測試缺少 ops 應拋出錯誤"""
        with pytest.raises(ValidationError):
            DeltaSchema()

    def test_invalid_ops_with_invalid_operation(self):
        """測試包含無效操作的 ops 應拋出錯誤"""
        with pytest.raises(ValidationError):
            DeltaSchema(ops=[
                {"insert": "valid"},
                {}  # 無效操作
            ])


class TestWebSocketMessageSchema:
    """WebSocket 消息 Schema 測試"""

    def test_valid_message(self):
        """測試有效的 WebSocket 消息"""
        message = WebSocketMessageSchema(
            delta={"ops": [{"insert": "Hello"}]}
        )
        assert message.delta.ops[0].insert == "Hello"

    def test_valid_message_complex_delta(self):
        """測試複雜 Delta 的 WebSocket 消息"""
        message = WebSocketMessageSchema(
            delta={
                "ops": [
                    {"retain": 10},
                    {"insert": "inserted text", "attributes": {"bold": True}},
                    {"delete": 5}
                ]
            }
        )
        assert len(message.delta.ops) == 3

    def test_invalid_missing_delta(self):
        """測試缺少 delta 應拋出錯誤"""
        with pytest.raises(ValidationError):
            WebSocketMessageSchema()

    def test_invalid_delta_format(self):
        """測試無效的 delta 格式"""
        with pytest.raises(ValidationError):
            WebSocketMessageSchema(delta={"invalid": "data"})

    def test_invalid_delta_empty_ops(self):
        """測試 delta 包含空 ops 應拋出錯誤"""
        with pytest.raises(ValidationError):
            WebSocketMessageSchema(delta={"ops": []})

    def test_invalid_delta_null(self):
        """測試 delta 為 null 應拋出錯誤"""
        with pytest.raises(ValidationError):
            WebSocketMessageSchema(delta=None)


class TestMessageSizeValidation:
    """消息大小驗證測試（Schema 層級的輔助測試）"""

    def test_large_insert_content(self):
        """測試大量內容的插入操作仍然有效（Schema 不限制大小）"""
        large_text = "x" * 10000
        message = WebSocketMessageSchema(
            delta={"ops": [{"insert": large_text}]}
        )
        assert len(message.delta.ops[0].insert) == 10000

    def test_many_operations_valid(self):
        """測試多個操作的 Delta（Schema 不限制數量）"""
        ops = [{"insert": f"text{i}"} for i in range(100)]
        message = WebSocketMessageSchema(delta={"ops": ops})
        assert len(message.delta.ops) == 100

    def test_message_size_calculation(self):
        """測試消息大小計算"""
        large_insert = "x" * 300000  # 300KB of text
        message_dict = {"delta": {"ops": [{"insert": large_insert}]}}
        size = len(json.dumps(message_dict).encode('utf-8'))
        assert size > 256 * 1024  # Should exceed 256KB limit


class TestRealWorldScenarios:
    """真實場景測試"""

    def test_quill_typical_delta(self):
        """測試 Quill 編輯器的典型 Delta 格式"""
        # 模擬用戶輸入 "Hello World" 並將 "World" 設為粗體
        delta = DeltaSchema(ops=[
            {"insert": "Hello "},
            {"insert": "World", "attributes": {"bold": True}},
            {"insert": "\n"}
        ])
        assert len(delta.ops) == 3

    def test_quill_header_formatting(self):
        """測試 Quill 標題格式化"""
        delta = DeltaSchema(ops=[
            {"insert": "Title"},
            {"insert": "\n", "attributes": {"header": 1}}
        ])
        assert delta.ops[1].attributes == {"header": 1}

    def test_quill_list_formatting(self):
        """測試 Quill 列表格式化"""
        delta = DeltaSchema(ops=[
            {"insert": "Item 1"},
            {"insert": "\n", "attributes": {"list": "bullet"}},
            {"insert": "Item 2"},
            {"insert": "\n", "attributes": {"list": "bullet"}}
        ])
        assert len(delta.ops) == 4

    def test_quill_image_embed(self):
        """測試 Quill 圖片嵌入"""
        delta = DeltaSchema(ops=[
            {"insert": {"image": "data:image/png;base64,..."}}
        ])
        assert isinstance(delta.ops[0].insert, dict)
        assert "image" in delta.ops[0].insert

    def test_quill_delete_and_insert(self):
        """測試 Quill 刪除並插入操作"""
        # 模擬選中文字後輸入新文字
        delta = DeltaSchema(ops=[
            {"retain": 5},
            {"delete": 10},
            {"insert": "replacement"}
        ])
        assert delta.ops[0].retain == 5
        assert delta.ops[1].delete == 10
        assert delta.ops[2].insert == "replacement"
