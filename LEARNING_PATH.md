# SyncDocs 學習路徑指南

> 本指南將幫助你循序漸進地理解這個即時協作文件編輯器的完整架構和實作細節。

## 學習目標

完成本專案的學習後，你將掌握：

- Django Ninja 現代化 API 開發
- WebSocket 即時通訊實作
- SvelteKit 全端框架應用
- JWT 認證機制
- 富文本編輯器整合（Quill.js）
- Docker 容器化部署

---

## 前置知識

| 知識領域 | 建議程度 | 備註 |
|---------|---------|------|
| Python 基礎 | 必須 | 函數、類別、裝飾器 |
| Django 基礎 | 建議 | ORM、模型、遷移 |
| JavaScript/TypeScript | 必須 | ES6+、Promise、async/await |
| HTTP/REST API | 建議 | GET、POST、PUT、DELETE |
| Svelte / WebSocket | 可選 | 可以邊學邊做 |

推薦學習資源：
- [Django 官方教學](https://docs.djangoproject.com/zh-hans/5.2/intro/tutorial01/)
- [Svelte 互動式教學](https://svelte.dev/tutorial)

---

## 學習路線圖

```
第一階段: 理解資料層        第二階段: REST API 層
       │                          │
       ├─ Models                  ├─ Django Ninja
       ├─ Database                ├─ Authentication
       └─ ORM 查詢                └─ CRUD Operations
                                       │
                                       ▼
第三階段: 前端基礎          第四階段: 即時協作
       │                          │
       ├─ SvelteKit               ├─ WebSocket
       ├─ 路由系統                ├─ Django Channels
       ├─ 元件設計                ├─ Quill Delta
       └─ 狀態管理                └─ 協作同步
                                       │
                                       ▼
第五階段: 整合與測試        第六階段: 部署與優化
       │                          │
       ├─ 前後端整合              ├─ Docker
       ├─ 錯誤處理                ├─ 生產環境配置
       └─ 測試編寫                └─ 效能優化
```

---

## 第一階段：理解資料層

### 階段目標
理解專案的資料結構和資料庫設計，這是整個系統的基礎。

### 學習內容

**1.1 資料模型設計**
- 閱讀檔案：`backend/docs_app/models.py`
- 關鍵概念：
  - `Document` 模型的欄位設計
  - `UUIDField` 為什麼比自增 ID 更適合分散式系統
  - `JSONField` 如何儲存 Quill Delta
  - `ForeignKey`（owner）vs `DocumentCollaborator` 中間模型（支援權限級別）

**1.2 版本歷史模型**
- 閱讀檔案：`backend/docs_app/models.py`（DocumentVersion 部分）
- 關鍵概念：
  - 完整快照 vs Delta diff 方案的取捨
  - `version_number` 自動遞增邏輯
  - `cleanup_old_versions()` 清理舊版本機制

**1.3 ORM 查詢練習**
- 閱讀檔案：`backend/docs_app/migrations/`

```bash
# 進入 Django shell 練習
docker exec -it <backend_container_id> python manage.py shell

# 練習查詢
from docs_app.models import Document
Document.objects.filter(owner=user)
```

### 階段檢查點
- [ ] 能解釋為什麼 `owner` 和 `shared_with` 需要不同的 `related_name`
- [ ] 能使用 Django ORM 查詢用戶擁有或被分享的所有文件
- [ ] 理解 `select_related` 和 `prefetch_related` 的差異

---

## 第二階段：REST API 層

### 階段目標
理解如何使用 Django Ninja 建構現代化的 RESTful API。

### 學習內容

**2.1 認證系統**
- 閱讀檔案：`backend/docs_app/auth_api.py`
- 關鍵概念：JWT Token 結構、Access Token vs Refresh Token
- 延伸閱讀：[JWT 介紹](https://jwt.io/introduction)、[Django Ninja JWT](https://eadwincode.github.io/django-ninja-jwt/)

**2.2 Django Ninja Schema**
- 閱讀檔案：`backend/docs_app/api.py`（Schema 部分）
- 關鍵概念：Pydantic Schema、請求驗證、響應序列化

**2.3 CRUD 操作**
- 閱讀檔案：`backend/docs_app/api.py`
- 關鍵概念：RESTful 設計、權限檢查模式、錯誤處理
- 實作練習：訪問 http://localhost:8000/api/docs 測試 API

**2.4 協作者管理**
- 繼續閱讀 `api.py` 的協作者相關端點
- 理解分享功能的實作

**2.5 版本歷史 API**
- 閱讀檔案：`backend/docs_app/api.py`（版本相關端點）
- 關鍵概念：
  - 版本列表、詳情、還原三個端點
  - `update_document` 自動創建版本的邏輯
  - 還原版本時創建新版本的設計決策

### 階段檢查點
- [ ] 能用 curl 或 Postman 測試註冊/登入 API
- [ ] 能解碼 JWT Token 並理解其內容
- [ ] 理解為什麼刪除操作需要 `owner_only=True`
- [ ] 理解版本還原為什麼會創建新版本

---

## 第三階段：前端基礎

### 階段目標
理解 SvelteKit 的架構和元件設計。

### 學習內容

**3.1 SvelteKit 路由系統**
- 研究檔案結構：`frontend/src/routes/`
- 關鍵概念：
  - 檔案系統路由
  - `(protected)` 路由群組（需要認證）
  - `[document_id]` 動態路由

**3.2 認證流程**
- 閱讀檔案：`frontend/src/lib/auth.ts`
- 關鍵概念：localStorage Token、HTTP 攔截器、自動添加認證標頭

**3.3 Quill 編輯器整合**
- 閱讀檔案：`frontend/src/lib/components/QuillEditor.svelte`
- 先閱讀：`Delta.md` 理解 Delta 概念
- 關鍵概念：
  - 第三方庫在 Svelte 中的整合
  - 為什麼 Quill 需要動態導入（SSR 限制）
  - Svelte 5 Runes 語法：`$state()`、`$derived()`、`$effect()`、`$props()`
  - `$bindable()` 實現雙向綁定（如 `bind:editor`）

**3.4 狀態管理與自動保存**
- 閱讀檔案：`frontend/src/routes/(protected)/docs/[document_id]/+page.svelte`
- 關鍵概念：Debounce 防抖、保存狀態機

**3.5 版本歷史面板**
- 閱讀檔案：`frontend/src/lib/components/VersionHistoryPanel.svelte`
- 閱讀檔案：`frontend/src/lib/api/versions.ts`
- 關鍵概念：
  - 側邊面板 UI 設計
  - `$effect()` 監聽 isOpen 變化載入版本
  - 還原後重新載入文件的流程

### 階段檢查點
- [ ] 理解 SvelteKit 檔案系統路由如何工作
- [ ] 能解釋 Svelte 5 的 `$props()` 和 `$bindable()` 如何實現雙向綁定
- [ ] 理解 `$state()`、`$derived()`、`$effect()` 的使用場景
- [ ] 理解 Delta 的三種操作（insert, retain, delete）
- [ ] 理解版本歷史面板如何與文件頁面整合

---

## 第四階段：即時協作

這是整個專案最核心和最複雜的部分。

### 階段目標
理解 WebSocket 通訊和即時協作的實作原理。

### 學習內容

**4.1 WebSocket 基礎**
- 理解 WebSocket vs HTTP：全雙工通訊 vs 請求/響應
- 實作觀察：打開瀏覽器 DevTools → Network → WS，觀察 WebSocket 訊息

**4.2 Django Channels Consumer**
- 閱讀檔案：`backend/docs_app/consumers.py`、`backend/docs_app/routing.py`
- 關鍵概念：
  - ASGI vs WSGI
  - Channel Layer 和 Group（同一文件的用戶在同一群組）
  - 為什麼需要 Redis（多伺服器實例間通訊）

**4.3 WebSocket 認證**
- 閱讀檔案：`backend/docs_app/auth_middleware.py`
- 關鍵概念：
  - 為什麼用 Query Parameter 而非 Header（瀏覽器 WebSocket API 限制）
  - Middleware 模式

**4.4 Delta 同步邏輯**
- 閱讀：`backend/docs_app/consumers.py` 的 `receive` 和 `doc_update` 方法
- 閱讀：`frontend/src/routes/(protected)/docs/[document_id]/+page.svelte` WebSocket 部分
- 關鍵概念：
  - 避免回聲（Echo Prevention）：不發送回給原始發送者
  - `source !== 'user'`：只發送用戶操作

**4.5 保存與同步**
- 閱讀：`backend/docs_app/api.py` 的 `_broadcast_document_saved` 方法
- 理解 HTTP API 和 WebSocket 的配合

**4.6 游標與在線狀態（Cursor Presence）**
- 閱讀檔案：`backend/docs_app/consumers.py` 的 `handle_cursor_move`、`add_presence`、`remove_presence` 方法
- 閱讀檔案：`frontend/src/lib/components/QuillEditor.svelte` 的 `setCursor`、`removeCursor` 方法
- 關鍵概念：
  - WebSocket 消息類型：`cursor_move`、`user_join`、`user_leave`、`presence_sync`
  - Redis Hash 管理在線用戶（`presence:{document_id}`）
  - TTL 機制確保活躍用戶不會消失
  - quill-cursors 套件整合（CSS 定位要點）
  - Svelte 5 Map 響應式注意事項（需創建新 Map 觸發更新）

### 階段檢查點
- [ ] 能解釋為什麼即時協作需要 WebSocket 而不是輪詢
- [ ] 理解 `self.channel_name` 和 `self.room_group_name` 的區別
- [ ] 能解釋 Delta 同步中如何避免無限循環
- [ ] 理解 cursor_move 為什麼不發回給發送者
- [ ] 能解釋 TTL 刷新機制的作用

---

## 第五階段：整合與測試

### 階段目標
理解測試的重要性和最佳實踐。

### 學習內容

**5.1 測試基礎**
- 閱讀：`backend/docs_app/tests/conftest.py`
- 關鍵概念：pytest fixtures、測試隔離

**5.2 API 測試**
- 閱讀：`backend/docs_app/tests/test_api.py`
- 學習如何測試 REST API 的正面和負面情況

**5.3 WebSocket 測試**
- 閱讀：`backend/docs_app/tests/test_consumers.py`
- 關鍵概念：異步測試、`@pytest.mark.asyncio`

**5.4 版本歷史測試**
- 閱讀：`backend/docs_app/tests/test_version_history.py`
- 關鍵概念：
  - 模型方法測試（create_version、cleanup_old_versions）
  - API 端點測試（list、detail、restore）
  - 權限測試（只讀用戶無法還原）

### 階段檢查點
- [ ] 能運行測試並看到覆蓋率報告
- [ ] 理解 fixture 的作用
- [ ] 能為新功能編寫測試
- [ ] 理解版本歷史測試的覆蓋場景

---

## 第六階段：部署與優化

這個階段是可選的，適合想深入了解生產環境的學習者。

### 學習內容

- **Docker 容器化**：閱讀 `docker-compose.yml`、`backend/Dockerfile`
- **環境變數管理**：閱讀 `backend/backend/settings.py`
- **效能優化**：N+1 查詢問題、快取策略

---

## 學習檢查清單

完成學習後，你應該能夠回答以下問題：

### 資料層
- [ ] `select_related` 和 `prefetch_related` 有什麼區別？
- [ ] 為什麼使用 UUID 作為主鍵？

### API 層
- [ ] Django Ninja 和 DRF 有什麼區別？
- [ ] JWT Token 包含哪些部分？為什麼需要 Refresh Token？

### 前端
- [ ] Svelte 5 Runes（`$state`、`$derived`、`$effect`）如何取代舊的 `$:` 語法？
- [ ] `$props()` 和 `$bindable()` 如何實現元件屬性和雙向綁定？
- [ ] 為什麼 Quill 需要在 `onMount` 中初始化？

### 即時協作
- [ ] WebSocket 和 HTTP 有什麼根本區別？
- [ ] Channel Layer 的作用是什麼？
- [ ] 如何避免 Delta 的無限循環？

---

## 學習建議與資源

### 學習方法
1. **按順序學習**：雖然想快速看到效果，但按順序能建立更扎實的基礎
2. **動手實作**：光看不練是學不會的，務必完成每個階段的練習
3. **善用調試工具**：`console.log`、`print()`、瀏覽器 DevTools、Django 日誌

### 遇到困難時
1. 查看日誌（後端 Django 日誌、前端 Console）
2. 使用調試工具（Django Debug Toolbar、Network 標籤）
3. 閱讀官方文檔
4. 簡化問題，逐一解決

### 官方文檔
- [Django](https://docs.djangoproject.com/)
- [Django Ninja](https://django-ninja.rest-framework.com/)
- [Django Channels](https://channels.readthedocs.io/)
- [SvelteKit](https://kit.svelte.dev/)
- [Quill.js](https://quilljs.com/docs/)

### 後續學習方向
- 實作 OT (Operational Transformation) 解決衝突
- 添加評論功能
- 學習 Redis、Celery、Kubernetes

---

**祝你學習愉快！每個專家都曾經是初學者，保持好奇心和耐心最重要。**
