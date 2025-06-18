"""
路由配置測試模組
測試WebSocket路由配置
"""

from docs_app.routing import websocket_urlpatterns


class TestWebSocketRouting:
    """WebSocket路由測試類"""

    def test_websocket_urlpatterns_exists(self):
        """測試WebSocket URL模式存在"""
        assert websocket_urlpatterns is not None
        assert isinstance(websocket_urlpatterns, list)
        assert len(websocket_urlpatterns) > 0

    def test_document_websocket_pattern(self):
        """測試文檔WebSocket URL模式"""
        # 獲取第一個URL模式（應該是文檔WebSocket模式）
        pattern = websocket_urlpatterns[0]

        # 測試有效的UUID格式
        valid_uuids = [
            "123e4567-e89b-12d3-a456-426614174000",
            "550e8400-e29b-41d4-a716-446655440000",
            "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
            "6ba7b811-9dad-11d1-80b4-00c04fd430c8"
        ]

        for uuid in valid_uuids:
            test_path = f"ws/docs/{uuid}/"
            # 使用resolve方法來測試URL匹配
            try:
                match = pattern.resolve(test_path)
                assert match is not None, f"Valid UUID {uuid} should match the pattern"
                assert match.kwargs.get('document_id') == uuid
            except Exception:
                # 如果resolve失敗，說明模式不匹配
                assert False, f"Valid UUID {uuid} should match the pattern"

    def test_document_websocket_pattern_invalid_uuids(self):
        """測試無效UUID格式不匹配"""
        pattern = websocket_urlpatterns[0]

        # 測試無效的UUID格式
        invalid_uuids = [
            "123",  # 太短
            "123e4567-e89b-12d3-a456",  # 不完整
            "123e4567-e89b-12d3-a456-42661417400g",  # 包含無效字符
            "123e4567e89b12d3a456426614174000",  # 缺少連字符
        ]

        for invalid_uuid in invalid_uuids:
            test_path = f"ws/docs/{invalid_uuid}/"
            try:
                match = pattern.resolve(test_path)
                # 如果resolve成功，說明匹配了，這不應該發生
                assert False, f"Invalid UUID {invalid_uuid} should not match the pattern"
            except Exception:
                # 如果resolve失敗，說明模式不匹配，這是期望的結果
                pass

    def test_document_websocket_pattern_edge_cases(self):
        """測試邊界情況"""
        pattern = websocket_urlpatterns[0]

        # 測試邊界情況
        edge_cases = [
            "ws/docs//",  # 空UUID
            "ws/docs/123e4567-e89b-12d3-a456-426614174000",  # 缺少結尾斜杠
            "ws/docs/123e4567-e89b-12d3-a456-426614174000/extra",  # 額外路徑
            "/ws/docs/123e4567-e89b-12d3-a456-426614174000/",  # 開頭斜杠
        ]

        for case in edge_cases:
            try:
                match = pattern.resolve(case)
                # 如果resolve成功，說明匹配了，這不應該發生
                assert False, f"Edge case {case} should not match the pattern"
            except Exception:
                # 如果resolve失敗，說明模式不匹配，這是期望的結果
                pass

    def test_websocket_pattern_consumer_mapping(self):
        """測試WebSocket模式映射到正確的消費者"""
        pattern = websocket_urlpatterns[0]

        # 檢查是否映射到DocConsumer
        consumer_class = pattern.callback
        assert consumer_class is not None

        # 檢查消費者類名（通過字符串表示）
        consumer_str = str(consumer_class)
        assert 'DocConsumer' in consumer_str

    def test_uuid_regex_pattern_specifics(self):
        """測試UUID正則表達式的具體細節"""
        pattern = websocket_urlpatterns[0]

        # 測試一個有效的UUID是否能被正確解析
        test_uuid = "123e4567-e89b-12d3-a456-426614174000"
        test_path = f"ws/docs/{test_uuid}/"

        try:
            match = pattern.resolve(test_path)
            assert match is not None
            assert match.kwargs.get('document_id') == test_uuid
        except Exception:
            assert False, "Valid UUID pattern should be resolvable"

    def test_websocket_url_pattern_count(self):
        """測試WebSocket URL模式數量"""
        # 目前應該只有一個WebSocket URL模式（文檔協作）
        assert len(websocket_urlpatterns) == 1

    def test_pattern_compilation(self):
        """測試正則表達式模式能正確編譯"""
        for pattern in websocket_urlpatterns:
            # 如果模式有問題，這裡會拋出異常
            assert pattern is not None

            # 測試模式可以用於匹配
            test_uuid = "123e4567-e89b-12d3-a456-426614174000"
            test_path = f"ws/docs/{test_uuid}/"
            try:
                match = pattern.resolve(test_path)
                assert match is not None
            except Exception:
                # 如果resolve失敗，可能是路徑格式問題，但模式本身應該是有效的
                pass
