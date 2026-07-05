# SyncDocs 學習路徑指南

> 本指南將幫助你循序漸進地理解這個即時協作文件編輯器的完整架構和實作細節。

## 學習目標

完成本專案的學習後，你將掌握：

- Django Ninja 現代化 API 開發
- WebSocket 即時通訊實作
- SvelteKit 全端框架應用
- JWT 認證機制
- 富文本編輯器整合（Quill.js）
- Pydantic AI 整合 LLM（結構化輸出、依賴注入、串流）
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
- [Django 官方教學](https://docs.djangoproject.com/zh-hans/stable/intro/tutorial01/)
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
第五階段: 整合與測試        第六階段: AI 整合
       │                          │
       ├─ 前後端整合              ├─ Pydantic AI
       ├─ 錯誤處理                ├─ 結構化輸出
       └─ 測試編寫                ├─ 依賴注入 / 工具
                                  └─ WebSocket 串流
                                       │
                                       ▼
              第七階段: 部署與優化
                     │
                     ├─ Docker
                     ├─ 生產環境配置
                     └─ 效能優化
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
- [ ] 能解釋為什麼 `owner` 和 `collaborators` 需要不同的 `related_name`
- [ ] 能使用 Django ORM 查詢用戶擁有或被分享的所有文件
- [ ] 理解 `select_related` 和 `prefetch_related` 的差異

---

## 第二階段：REST API 層

### 階段目標
理解如何使用 Django Ninja 建構現代化的 RESTful API。

### 學習內容

**2.1 認證系統**
- 閱讀檔案：`backend/docs_app/auth_api.py`、`backend/docs_app/throttling.py`、`backend/backend/urls.py`
- 關鍵概念：JWT Token 結構、Access Token vs Refresh Token
- API 端點來源：
  | 功能 | 端點 | 來源 |
  |------|------|------|
  | 登入 | `/api/token/pair` | TokenController (auth_api.py，帶 IP 限流) |
  | 刷新 | `/api/token/refresh` | TokenController（繼承自 NinjaJWTDefaultController） |
  | 註冊 | `/api/auth/register` | AuthController (auth_api.py，帶 IP 限流) |
  | 登出 | `/api/auth/logout` | AuthController (auth_api.py) |
  | 當前用戶 | `/api/auth/me` | AuthController (auth_api.py) |
- Token 生命週期設計：
  - Access token 只有 30 分鐘且無法撤銷；撤銷能力靠 refresh token 黑名單
  - 登出時前端把 refresh token 送交後端加入黑名單（`ninja_jwt.token_blacklist`），立即失效
  - `ROTATE_REFRESH_TOKENS`：每次 refresh 換發新 refresh token、舊的進黑名單，
    前端必須同步保存新 refresh token，否則下次 refresh 直接失敗
  - 登入/註冊限流掛在 ninja 的 `throttle` 參數上（body 解析前執行）——
    ninja_jwt 的密碼驗證發生在 schema 驗證階段，限流放端點函數內會漏計失敗的登入嘗試
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
- 權限變更即時生效：變更/移除協作者時廣播 `permission_changed` 事件，
  consumer 對被變更用戶的既有 WS 連線即時更新 `can_write` 或直接斷線
  （WS 權限是連線時快照，不廣播的話被移除者既有連線仍可繼續收發編輯）

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
- 關鍵概念：
  - localStorage 存儲 Access Token 與 Refresh Token
  - HTTP 攔截器：自動添加認證標頭
  - 401 自動刷新：`apiFetch` 遇到 401 時用 Refresh Token 換取新 Access Token 並重試
  - `refreshPromise` 鎖防止多個請求同時觸發刷新

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
  - 還原透過 `doc_restored` 廣播同步所有在線協作者（清除 pending 編輯狀態 + 重置編輯器），避免其他人的 debounce PUT 把還原結果蓋回去

**3.6 評論面板**
- 閱讀檔案：`frontend/src/lib/components/CommentPanel.svelte`
- 閱讀檔案：`frontend/src/lib/api/comments.ts`
- 關鍵概念：
  - 評論列表顯示與回覆功能
  - WebSocket 即時同步評論（comment_add、comment_update、comment_delete 事件）
  - 權限判斷（is_author、can_delete）

### 階段檢查點
- [ ] 理解 SvelteKit 檔案系統路由如何工作
- [ ] 能解釋 Svelte 5 的 `$props()` 和 `$bindable()` 如何實現雙向綁定
- [ ] 理解 `$state()`、`$derived()`、`$effect()` 的使用場景
- [ ] 理解 Delta 的三種操作（insert, retain, delete）
- [ ] 理解版本歷史面板如何與文件頁面整合
- [ ] 理解評論系統的 WebSocket 即時同步機制

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
  - 為什麼用 Subprotocol 傳遞 Token
    - 瀏覽器 WebSocket API 不支持自定義 Header
    - Subprotocol 比 Query Parameter 更安全（Token 不會出現在 URL 和伺服器日誌中）
  - 前端連接方式：`new WebSocket(url, ['access_token.<JWT>'])`
  - Middleware 模式：`JWTAuthMiddleware` 解析 subprotocol 並驗證 token
  - TOKEN_EXPIRED 處理：前端收到 4002 關閉碼時，先嘗試用 Refresh Token 換新 Access Token 再重連，而非直接登出

**4.4 WebSocket 自動重連機制**
- 閱讀檔案：`frontend/src/routes/(protected)/docs/[document_id]/+page.svelte` 的 `connectWebSocket`、`scheduleReconnect`、`getReconnectDelay` 方法
- 關鍵概念：
  - 指數退避 + 隨機抖動（Exponential Backoff + Jitter）避免伺服器雪崩
  - 正常關閉（1000/1001）和永久性錯誤（4001-4008）不重連
  - 暫時性錯誤自動重連，最多 5 次
  - TOKEN_EXPIRED（4002）refresh 成功後的重連也走同一套退避與次數上限，
    避免 token 剛換發又立即被拒絕時無限緊迴圈狂打 refresh 端點（自我 DoS）
  - 退避計數器在收到 `connection_success` 才歸零：後端拒絕連線時會先 accept
    再 close，若在 onopen 歸零，被拒絕的連線也會重置退避
  - 重連前清理舊 socket 防止連線洩漏

**4.5 Delta 同步邏輯**
- 閱讀：`backend/docs_app/consumers.py` 的 `receive` 和 `doc_update` 方法
- 閱讀：`frontend/src/routes/(protected)/docs/[document_id]/+page.svelte` WebSocket 部分
- 關鍵概念：
  - 避免回聲（Echo Prevention）：不發送回給原始發送者
  - `source !== 'user'`：只發送用戶操作

**4.6 保存與同步**
- 閱讀：`backend/docs_app/api.py` 的 `_broadcast_document_saved` 方法
- 理解 HTTP API 和 WebSocket 的配合

**4.7 游標與在線狀態（Cursor Presence）**
- 閱讀檔案：`backend/docs_app/consumers.py` 的 `handle_cursor_move`、`add_user_to_presence`、`remove_user_from_presence` 方法
- 閱讀檔案：`frontend/src/lib/components/QuillEditor.svelte` 的 `setCursor`、`removeCursor` 方法
- 關鍵概念：
  - WebSocket 消息類型：`cursor_move`、`user_join`、`user_leave`、`presence_sync`
  - Redis Hash 管理在線用戶（`presence:{document_id}`）
  - Field 級 TTL 機制（HEXPIRE）：心跳只續命自己的 field，活躍用戶不會消失，異常斷線殘留的 ghost user 會獨立過期
  - 連接數追蹤（`ws:connections:user:{user_id}`）採同一機制：TTL 掛在各自的 channel field 上，
    ghost 連線獨立過期，不會累積撞 max_connections 誤鎖用戶
  - quill-cursors 套件整合（CSS 定位要點）
  - Svelte 5 Map 響應式注意事項（需創建新 Map 觸發更新）

### 階段檢查點
- [ ] 能解釋為什麼即時協作需要 WebSocket 而不是輪詢
- [ ] 理解 `self.channel_name` 和 `self.room_group_name` 的區別
- [ ] 能解釋 Delta 同步中如何避免無限循環
- [ ] 理解 cursor_move 為什麼不發回給發送者
- [ ] 能解釋 TTL 刷新機制的作用
- [ ] 能解釋為什麼重連需要指數退避 + 隨機抖動（防止伺服器雪崩）
- [ ] 理解 TOKEN_EXPIRED 時的自動刷新重連流程

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

**5.5 評論系統測試**
- 閱讀：`backend/docs_app/tests/test_comments.py`
- 關鍵概念：
  - 評論 CRUD 操作測試
  - 回覆功能測試（parent_id）
  - 權限測試（作者/文件擁有者可刪除）
  - WebSocket 即時通知測試

### 階段檢查點
- [ ] 能運行測試並看到覆蓋率報告
- [ ] 理解 fixture 的作用
- [ ] 能為新功能編寫測試
- [ ] 理解版本歷史測試的覆蓋場景
- [ ] 理解評論系統測試的權限驗證邏輯

---

## 第六階段：AI 整合（Pydantic AI）

### 階段目標
理解如何用 Pydantic AI 把 LLM 能力整合進應用，並掌握純文字、結構化輸出、依賴注入與串流四種模式。

### 學習內容

**6.1 AI 服務層與供應商切換**
- 閱讀檔案：`backend/docs_app/ai_service.py`、`backend/backend/settings.py`（`AI_PROVIDER` 相關）
- 先閱讀：`README.md` 的「AI 供應商設定」段落
- 關鍵概念：
  - Pydantic AI Agent 抽象：同一份程式碼接 NVIDIA NIM（OpenAI 相容端點）或 Gemini（Google 原生 SDK）
  - 惰性初始化（lazy init）：model / agent 首次使用才建立，避免 import 時就要求 API key
  - 為什麼用全域單例共用 model（不重複建立連線）
  - 輸入截斷（≤5000 字元）控制 token 成本

**6.2 純文字處理（摘要 / 潤稿）**
- 閱讀檔案：`backend/docs_app/ai_api.py`（`process_text`）、`ai_service.py`（`process`）
- 關鍵概念：
  - `PROMPTS` 模板組合
  - `agent.run()` 回傳純文字 `result.output`
  - 錯誤處理：429 配額用盡 vs 服務暫時無法使用 vs 未配置

**6.3 結構化輸出（校對 / 文件分析）**
- 閱讀檔案：`ai_service.py`（`proofread`、`generate_metadata`）、`schemas.py`（`ProofreadResult`、`DocumentMetadata`）
- 關鍵概念：
  - `output_type=PydanticModel` 取得型別安全的結構化結果（自動驗證 + 重試）
  - 同一個 pydantic model 既當 agent 輸出、又當 API 回應 schema
  - 相較純文字，結構化輸出讓前端能逐項渲染（校對建議、metadata 欄位）

**6.4 依賴注入與工具（文件問答）**
- 閱讀檔案：`ai_service.py`（`ask`、`DocDeps`、`get_document_text` 工具）、`ai_api.py`（`ask_document`）
- 關鍵概念：
  - `deps_type=DocDeps` 把整份文件當依賴注入
  - `@agent.tool` 讓 agent 主動呼叫工具讀取文件內容（`RunContext.deps`）
  - 與直接把文件塞進 prompt 的差異：工具模式讓模型自行決定何時取用

**6.5 WebSocket AI 串流（打字機效果）**
- 閱讀檔案：`ai_service.py`（`process_stream`、`ask_stream`）、`consumers.py`（`ai_stream` / `ai_ask_stream` / `ai_stream_cancel`）
- 閱讀檔案：`frontend/src/lib/components/AIDialog.svelte`、`AIAskDialog.svelte`、文件頁 `+page.svelte`（`ai_stream_*` 訊息）
- 關鍵概念：
  - 為什麼串流走既有 `DocConsumer`（複用 JWT 認證與限流）而非 HTTP
  - `agent.run_stream()` + `stream_text(delta=True)` 逐塊 yield（摘要/潤稿走 `process_stream`，文件問答走 `ask_stream`，後者複用 deps + 工具的 doc agent）
  - chunk 只回給發送者本人（`self.send`，不經 `group_send`）
  - 摘要/潤稿與文件問答共用 consumer 的泛用串流封裝 `_run_ai_stream()`，差別只在串流來源與輸入驗證
  - 可取消的背景 asyncio 任務：使用者停止生成 / 斷線時清理
  - 與 HTTP `/ai/process` 共用同一 Redis 速率限制額度

**6.6 速率限制與測試**
- 閱讀檔案：`backend/docs_app/ai_rate_limiter.py`、`tests/test_ai_api.py`
- 關鍵概念：
  - 四個 HTTP 端點 + 串流共用額度鍵 `ai:{user_id}`（每用戶 10 次 / 60 秒）
  - fail-open 策略（與 WebSocket 連接管理 fail-closed 的差異與理由）
  - 測試以 `TestModel` / `FunctionModel` + `agent.override()` 取代對 SDK 內部的脆弱 mock

### 階段檢查點
- [ ] 能說明 Pydantic AI 如何用同一份程式碼切換不同 LLM 供應商
- [ ] 理解 `output_type` 結構化輸出相較純文字回傳的優勢
- [ ] 能解釋文件問答為何用依賴注入 + 工具，而非直接把文件塞進 prompt
- [ ] 理解 AI 串流為什麼走 WebSocket 而非 HTTP
- [ ] 能說明 AI 速率限制為何採 fail-open

---

## 第七階段：部署與優化

這個階段是可選的，適合想深入了解生產環境的學習者。

### 學習內容

- **Docker 容器化**：閱讀 `docker-compose.yml`、`docker-compose.override.yml`、`backend/Dockerfile`
- **開發/生產環境分離**：
  - `docker-compose.yml`：生產基礎配置，使用 Daphne ASGI 伺服器
  - `docker-compose.override.yml`：開發覆蓋配置，使用 runserver（支援熱重載）
  - `docker compose up` 自動載入 override（開發模式）
  - `docker compose -f docker-compose.yml up` 僅用基礎配置（生產模式）
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

### AI 整合
- [ ] Pydantic AI 如何用同一份程式碼切換不同 LLM 供應商？
- [ ] `output_type` 結構化輸出帶來什麼好處？
- [ ] 文件問答為什麼用依賴注入 + 工具，而非直接把文件塞進 prompt？

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
- 學習 Redis、Celery、Kubernetes

---

**祝你學習愉快！每個專家都曾經是初學者，保持好奇心和耐心最重要。**
