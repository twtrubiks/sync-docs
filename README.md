# SyncDocs - 即時協作文件編輯器

[English Version](README_en.md)

SyncDocs 是一款受 Google Docs 啟發、基於現代技術堆疊打造的網頁協作文件編輯器。它允許使用者即時與他人建立、編輯和共享文件。

該專案利用 Django Ninja 建構高效能的後端 API，並使用 SvelteKit 提供反應式且快速的前端使用者介面。

本專案使用 [Cline](https://github.com/twtrubiks/mcp-vscode-cline?tab=readme-ov-file#cline) 完成, 可參考 [.clinerules/MVP_Development.md](.clinerules/MVP_Development.md)

## 畫面截圖

![alt tag](https://cdn.imgpile.com/f/wqSGcM2_xl.png)

即時更新

![alt tag](https://cdn.imgpile.com/f/eoPjnL3_xl.png)

可以共用文件

![alt tag](https://cdn.imgpile.com/f/qVOuhaq_xl.png)

## ✨ 主要功能

* **即時協作**：多位使用者可同時編輯同一份文件，變更會即時反映給所有參與者，由 Django Channels 提供支援。
* **豐富文本編輯**：基於 [Quill.js Delta 的核心技術結構](Delta.md) 的簡潔直觀編輯器，支援多種格式選項。
* **使用者驗證**：安全的用戶註冊和登入系統。
* **文件管理**：使用者可以從個人儀表板建立、查看和管理自己的文件。
* **文件共享**：輕鬆與其他使用者共享文件。
* **快速且現代化的技術堆疊**：後端 API 使用 Django Ninja，前端使用 SvelteKit，確保高效能和現代化的開發體驗。

## 🛠️ 技術堆疊

### 後端

* **框架**：[Django](https://github.com/twtrubiks/django-tutorial) 搭配 [Django Ninja](https://github.com/twtrubiks/django_ninja_tutorial) 建構 REST API
* **即時通訊**：[Django Channels](https://github.com/twtrubiks/django-chat-room) 處理 WebSocket
* **資料庫**：PostgreSQL（Docker 環境預設使用）
* **非同步伺服器**：Uvicorn/Daphne
* **依賴套件**：
  * `django`
  * `django-ninja`
  * `channels`
  * `channels-redis`

### 前端

* **框架**：[SvelteKit](https://kit.svelte.dev/)
* **語言**：TypeScript
* **豐富文本編輯器**：[Quill.js](https://quilljs.com/)
* **樣式**： Tailwind CSS

## 📂 專案結構

專案主要分為兩個目錄：

```cmd
.
├── backend/      # 包含 Django 專案
│   ├── docs_app/ # 處理文件和使用者的核心 Django 應用程式
│   └── backend/  # Django 專案設定
└── frontend/     # 包含 SvelteKit 專案
    ├── src/
    │   ├── routes/ # SvelteKit 基於檔案的路由
    │   └── lib/    # Svelte 元件和工具函數
```

## 🚀 本地開發設定

請依照以下步驟在您的本機電腦上設定並執行專案。

### 先決條件

* [Python](https://www.python.org/downloads/) 3.12+
* [Node.js](https://nodejs.org/) 18+ 和 npm (或 pnpm/yarn)
* [Redis](https://redis.io/docs/getting-started/installation/) (用於即時協作功能)

### 快速啟動 (使用 Docker, 建議用這個)

```cmd
docker compose up --build
```

### 本地開發 (不使用 Docker)

## 1. 後端設定

```bash
# 前往 backend 目錄
cd backend

# 建立並啟用虛擬環境
python -m venv venv
source venv/bin/activate  # Windows 請使用 `venv\Scripts\activate`

# 安裝 Python 依賴套件
pip install -r requirements.txt

# 套用資料庫遷移
python manage.py migrate

# 啟動 Django 開發伺服器
# API 將可在 http://127.0.0.1:8000 取得
python manage.py runserver
```

## 2. 前端設定

開啟一個新的終端機視窗。

```bash
# 前往 frontend 目錄
cd frontend

# 安裝 Node.js 依賴套件
npm install

# 啟動 SvelteKit 開發伺服器
# 前端將可在 http://localhost:5173 取得
npm run dev -- --open
```

### 存取應用程式

* **前端**：開啟瀏覽器並前往 `http://localhost:5173`。
* **後端 API 文件**：自動產生的 API 文件可在 `http://127.0.0.1:8000/api/docs` 取得。

### 📖 API 文件

後端 API 使用 Django Ninja 建構，它提供自動化的互動式文件 [http://127.0.0.1:8000/api/docs](http://127.0.0.1:8000/api/docs)

![alt tag](https://cdn.imgpile.com/f/rgw7Ll0_xl.png)

### 運行測試

使用 Docker 運行測試

```cmd
docker compose --profile testing up
```

在本地運行測試

```cmd
pytest --cov=. --cov-report=html
```

![alt tag](https://cdn.imgpile.com/f/JvWwDwA_md.png)

## 📚 學習資源

本專案作為**教學示範項目**，提供完整的學習文檔幫助你理解系統設計和實作細節：

### 核心文檔

* **[📖 學習路徑指南 (LEARNING_PATH.md)](LEARNING_PATH.md)**
  * 📋 6 個階段的循序漸進學習計畫
  * 🎯 每個階段的檢查點和實作練習
  * 💡 關鍵代碼的詳細解釋和教學註釋
  * ⏱️ 預計學習時間：15-20 天
  * 🎓 適合：全端開發初學者、想學習即時協作功能的開發者

* **[🏗️ 架構設計文檔 (ARCHITECTURE.md)](ARCHITECTURE.md)**
  * 🎨 完整的系統架構圖和數據流程圖
  * 🤔 技術選型理由和對比分析
  * 🎭 設計模式的實際應用（Repository、Observer、Middleware...）
  * 🔐 安全性設計和效能優化策略
  * 📊 架構決策記錄 (ADR)
  * 🎓 適合：中級開發者、架構師、面試準備

* **[⚙️ Quill.js Delta 核心技術 (Delta.md)](Delta.md)**
  * 🔍 深入理解 Delta 資料模型
  * 💡 為什麼選擇 Delta 而非 HTML
  * 🤝 Delta 如何支援即時協作
  * 🎓 適合：想理解富文本編輯器原理的開發者

### 開發文檔

* **[📋 MVP 開發清單 (.clinerules/MVP_Development.md)](.clinerules/MVP_Development.md)**
  * 完整的開發階段規劃
  * 前後端功能清單

### 建議閱讀順序

1. 🎯 **初學者**：Delta.md → LEARNING_PATH.md（跟著步驟學習）
2. 🏗️ **有經驗的開發者**：ARCHITECTURE.md → LEARNING_PATH.md（選擇性深入）
3. 👨‍🏫 **教師/講師**：ARCHITECTURE.md（課程大綱）+ LEARNING_PATH.md（教學進度）

### 🔮 未來規劃

此專案為 MVP (最小可行性產品)，尚有許多改進空間。以下是一些未來可能的功能：

* **在線狀態指示**：顯示目前正在查看或編輯文件的使用者。
* **游標位置顯示**：即時顯示協作者的游標。
* **文件版本歷史**：允許使用者查看並還原至文件的先前版本。
* **資料夾組織**：實作資料夾系統以更好地管理文件。
* **部署**：使用 Docker、Gunicorn 和 Nginx 建立生產就緒的部署設定。
* **全面測試**：新增更多單元測試和端對端測試以確保穩定性。

## Donation

文章都是我自己研究內化後原創，如果有幫助到您，也想鼓勵我的話，歡迎請我喝一杯咖啡 :laughing:

綠界科技ECPAY ( 不需註冊會員 )

![alt tag](https://payment.ecpay.com.tw/Upload/QRCode/201906/QRCode_672351b8-5ab3-42dd-9c7c-c24c3e6a10a0.png)

[贊助者付款](http://bit.ly/2F7Jrha)

歐付寶 ( 需註冊會員 )

![alt tag](https://i.imgur.com/LRct9xa.png)

[贊助者付款](https://payment.opay.tw/Broadcaster/Donate/9E47FDEF85ABE383A0F5FC6A218606F8)

## 贊助名單

[贊助名單](https://github.com/twtrubiks/Thank-you-for-donate)

## License

MIT license
