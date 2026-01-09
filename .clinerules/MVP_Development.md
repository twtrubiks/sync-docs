# MVP 開發清單：類 Google Docs 協作文件編輯器 (Django Ninja + SvelteKit)

**目標：** 快速驗證核心功能，包括基本的文件編輯、保存、**分享**、以及初步的即時協作。

**技術棧核心：**

* **後端 API：** Django Ninja (運行於 Django)
* **資料庫：** **SQLite** (適用於 MVP 階段)
* **前端應用程式：** SvelteKit (使用 Svelte)
* **富文本編輯器：** Quill.js
* **即時通訊：** Django Channels

## Phase 1: 核心後端 API - 使用者與文件管理 (Django Ninja)

* **使用者認證 (Django 內建 + Django Ninja 整合)**
  * 使用 Django 內建 `User` 模型。
  * 建立 Django Ninja API 端點用於：
    * 使用者註冊 (可使用 Pydantic schema 定義請求/響應)
    * 使用者登入 (返回 token，例如 JWT 或 Django Ninja 內建的 Session/Token Auth)
    * 使用者登出
  * 設定 API 的認證保護 (e.g., `HttpBearer` for JWT)。
* **文件資料模型 (Django ORM for SQLite)**
  * `Document` 模型：
    * `title` (CharField)
    * `owner` (ForeignKey to User)
    * `content` (JSONField 或 TextField)
    * `created_at` (DateTimeField auto_now_add)
    * `updated_at` (DateTimeField auto_now)
    * `collaborators` 欄位（透過 `DocumentCollaborator` 中間模型，支援 read/write 權限級別），用來記錄可以協作的使用者。
* **Pydantic Schemas (用於 Django Ninja)**
  * `DocumentSchema`, `DocumentCreateSchema`, `DocumentUpdateSchema`
  * `ShareRequestSchema` (用來接收要分享的使用者 username) 和 `UserSchema` (用於在分享列表中顯示使用者)。
* **文件操作 API 端點 (Django Ninja Router)**
  * `POST /api/documents/`: 創建新文件
  * `GET /api/documents/`: 取得使用者擁有或被分享的文件列表
  * `GET /api/documents/{document_id}/`: 取得特定文件內容
  * `PUT /api/documents/{document_id}/`: 更新文件內容
    * `GET /api/documents/{document_id}/collaborators/`: 獲取當前協作者列表。
    * `POST /api/documents/{document_id}/collaborators/`: 新增協作者到文件。
    * `DELETE /api/documents/{document_id}/collaborators/{user_id}/`: 移除協作者。
* **Django Admin 設定**
  * 註冊 `Document` 模型到 Django Admin Panel。

## Phase 2: 前端 - 編輯器界面實作 (SvelteKit + Quill.js)

* **SvelteKit 專案結構與路由設定**
  * 規劃檔案系統路由：
    * `/login` (登入頁面)
    * `/register` (註冊頁面)
    * `/dashboard` (文件列表/儀表板，需登入)
    * `/docs/{document_id}` (文件編輯器頁面，需登入)
  * 設定共享佈局 (`+layout.svelte`)，例如包含導航欄。
  * 設定需要身份驗證的頁面的路由守衛
* **使用者認證流程 (SvelteKit)**
  * 建立登入/註冊表單組件。
  * 呼叫 Django Ninja 的認證 API。
  * 在客戶端儲存認證 token (`localStorage` Cookie - 後者更安全但設定稍複雜)。
  * 設定 SvelteKit `fetch` 請求時自動帶上認證 token。
  * 實現登出功能。
* **富文本編輯器整合 (Quill.js in SvelteKit Component - Svelte 5 Runes)**
  * 建立一個名為 `QuillEditor.svelte` 的組件。
  * 使用 Svelte 5 Runes 語法：
    * `$props()` + `$bindable()` 實現雙向綁定 (`bind:value`, `bind:editor`)
    * `$effect()` 監聽內容變化並同步到編輯器
    * callback props 取代 `createEventDispatcher` 處理事件
  * 在該組件中初始化 Quill.js，配置基本工具列。
  * 實現獲取 Quill 編輯器內容 (Delta 格式)。
* **文件操作流程 (SvelteKit)**
  * **儀表板頁面 (`/dashboard/+page.svelte`):**
    * 呼叫 `GET /api/documents/` 獲取文件列表並顯示。
    * "創建新文件" 按鈕，呼叫 `POST /api/documents/` 並跳轉到新文件的編輯頁面。
  * **編輯器頁面 (`/docs/{document_id}/+page.svelte` - Svelte 5 Runes):**
    * 從路由參數獲取 `document_id`。
    * 使用 `$state()` 管理響應式狀態（標題、內容、保存狀態等）
    * 使用 `$derived.by()` 計算派生狀態（如狀態文字顯示）
    * 使用 `$effect()` 實現自動保存邏輯（防抖 1.5 秒）
    * 呼叫 `GET /api/documents/{document_id}/` 獲取文件內容並載入到 `QuillEditor` 組件。
    * 自動保存邏輯，將 Quill 內容 (Delta) 通過 `PUT /api/documents/{document_id}/` 保存到後端。
* **分享功能界面 (SvelteKit)**
  * 在文件編輯器頁面新增一個「共用」按鈕。
    * 點擊「共用」按鈕後，彈出一個對話框 (Modal)。
    * 對話框中包含：
      * 一個可複製的「分享連結」(就是當前頁面的 URL)。
      * 一個輸入框，用來輸入其他使用者的 email 或 username。
      * 一個「新增協作者」按鈕，呼叫後端新增協作者 API。
      * 一個列表，顯示目前所有協作者，並可呼叫 API 將其移除。
* **UI 模仿 Google Docs (MVP 級別)：**
  * 使用 SvelteKit 的組件化能力建構簡潔的界面。
  * 專注於編輯區域的可用性。

## Phase 3: 即時協作基礎 (Django Channels & SvelteKit)

* **WebSocket Consumer (Django Channels)**
  * `DocConsumer` 用於處理特定文件的 WebSocket 連接。
  * `connect()`: 更新身份驗證邏輯，允許 `owner` 或在 `collaborators` 列表中的使用者建立 WebSocket 連線並加入協作 Channel Group。
  * `disconnect()`: 從 Channel Group 移除。
  * `receive_json()`: 接收來自客戶端的編輯操作 (Quill Delta)並廣播。
* **SvelteKit 端 WebSocket 整合 (Svelte 5 Runes)**
  * 在文件編輯器頁面 (`/docs/{document_id}/+page.svelte`) 中：
    * 使用 `$state()` 管理 WebSocket 連接狀態
    * 在 `onMount()` 建立 WebSocket 連接到 Django Channels 的 `DocConsumer`
    * **發送更改：** 通過 callback props (`onTextChange`) 監聽 Quill 編輯器的 `text-change` 事件，獲取 Delta，並通過 WebSocket 發送給後端。
    * **接收更改：** 監聽 WebSocket 訊息，接收到其他用戶的 Delta 後，使用 `editor.updateContents(delta, 'silent')` 應用到本地編輯器（避免觸發本地事件）。
* **(MVP 簡化) 衝突處理：**
  * 依賴伺服器廣播的順序，或 "最後編輯者獲勝" 的隱含邏輯。不實現複雜的 OT/CRDT。

## Django Ninja 和 SvelteKit 的關鍵考量

* **Django Ninja Schemas:** 充分利用 Pydantic schema 進行數據驗證和序列化，能大大提高 API 的健壯性和開發效率。
* **SvelteKit Load Functions:** 使用 SvelteKit 的 `load` 函數 (`+page.server.js` 或 `+layout.server.js`) 在伺服器端或客戶端載入頁面所需數據，這有助於數據預取和更好的用戶體驗。
* **Svelte 5 Runes 與 Stores:** 使用 `$state()` 管理組件狀態，Svelte stores 管理全局狀態（如認證狀態）。`$store` 自動訂閱語法在 Svelte 5 仍然支援。
* **API 版本控制 (Django Ninja):** 雖然 MVP 可能不需要，但長遠來看，Django Ninja 容易實現 API 版本控制。
* **CORS (跨域資源共享):** 如果 Django 和 SvelteKit 在開發時運行在不同端口，或生產環境中部署在不同域名，需要在 Django (例如使用 `django-cors-headers`) 中正確配置 CORS。
