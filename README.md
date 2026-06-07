# 科研学习一体化网站 MVP

这个仓库现在只保存网站程序、部署配置和辅助脚本；用户论文、PDF、Markdown 笔记、缓存和报告放在独立知识库目录中。

- `backend/`：FastAPI API，负责论文管理、导入导出、搜索、AI 精读和问答。
- `frontend/`：React + Vite 工作台界面。
- `deploy/`：腾讯云服务器 Docker Compose 部署文件。
- `Scripts/`：本地辅助脚本和知识库迁移脚本。

默认知识库目录：

```text
/data/paper-agent/knowledge_base/
├─ papers/
│  ├─ pdf/
│  └─ notes/
├─ indexes/
├─ reports/
├─ assets/
│  └─ figures/
└─ cache/
   ├─ pdf_text/
   └─ mineru/
```

## 本地运行

后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:APP_PASSWORD="change-me"
$env:KNOWLEDGE_BASE_DIR="D:\AIworld\paper-agent\knowledge_base"
uvicorn app.main:app --reload
```

前端：

```powershell
cd frontend
npm install
npm run dev
```

默认登录账号是 `admin`，密码来自 `APP_PASSWORD`，不设置时是 `change-me`。

首次进入后点击“导入知识库”，会从 `KNOWLEDGE_BASE_DIR` 里的 `metadata/library.json` 导入论文元数据到网站数据库。

## 本地迁移

先 dry-run 检查，不写文件：

```powershell
python Scripts/migrate_knowledge_base.py --target D:\AIworld\paper-agent\knowledge_base
```

确认无误后再执行：

```powershell
python Scripts/migrate_knowledge_base.py --target D:\AIworld\paper-agent\knowledge_base --apply
```

默认不会复制旧 `Papers/*.md` 精读笔记，也不会复制 MinerU 缓存；后续可以在网站里重新生成精读笔记。

## 腾讯云部署

```bash
sudo mkdir -p /data/paper-agent/knowledge_base
cd deploy
cp .env.example .env
# 修改 .env 里的密码、JWT_SECRET、DeepSeek、DashScope 配置
docker compose up -d --build
```

生产环境建议在腾讯云安全组只开放 80/443/SSH，并在 Nginx 前面接 HTTPS。
