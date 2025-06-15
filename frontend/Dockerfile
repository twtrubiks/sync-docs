FROM node:22-alpine

# 設定工作目錄
WORKDIR /app

# 複製 package.json 和 lock 檔
COPY package*.json ./

# 安裝依賴
RUN npm install

# 複製專案的其餘程式碼
# 同樣地，這行主要是為了建檔，開發時會被 volume 覆蓋
COPY . .

# 開放 SvelteKit 開發伺服器預設的 5173 port
EXPOSE 5173

# 預設啟動指令
# 加上 --host 讓容器外部可以存取
CMD ["npm", "run", "dev", "--", "--host"]