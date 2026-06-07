# No-domain Tencent Cloud deployment

This project can run publicly without a domain by using the Tencent Cloud CVM public IP:

```text
http://YOUR_SERVER_IP
```

## 1. Server firewall

In the Tencent Cloud security group, open only:

- `22` for SSH
- `80` for the web app

Keep these ports closed to the public internet:

- `8000` backend
- `5432` Postgres
- `6379` Redis

## 2. Put code on GitHub

Use GitHub for code updates only. Do not put paper PDFs, notes, local env files, or generated runtime data into GitHub.

This project already ignores the important local data paths:

- `knowledge_base/`
- `Papers/`
- `Reports/`
- `Indexes/`
- `Assets/Figures/`
- `.env`
- `deploy/.env`
- `frontend/node_modules/`
- `frontend/dist/`

If this folder is not a git repository yet, initialize it locally and push it to GitHub:

```powershell
cd D:\AIworld\mybrain
git init
git add .
git commit -m "Initial deployment setup"
git branch -M main
git remote add origin git@github.com:YOUR_GITHUB_USER/YOUR_REPO.git
git push -u origin main
```

If you use HTTPS instead of SSH, replace the `git remote add origin` URL with the HTTPS URL from GitHub.

## 3. Prepare the server

Clone the GitHub repository to the server, for example:

```bash
cd /opt
git clone git@github.com:YOUR_GITHUB_USER/YOUR_REPO.git mybrain
```

Then create the data directory:

```bash
cd /opt/mybrain/deploy
bash server-init.sh
```

The paper data directory on the server is:

```text
/data/paper-agent/knowledge_base
```

Docker mounts it into the backend container as:

```text
/knowledge_base
```

## 4. Configure production env

Create the real env file:

```bash
cd /opt/mybrain/deploy
cp .env.example .env
```

Edit `.env` and replace:

```text
CORS_ORIGINS=http://YOUR_SERVER_IP
```

Also change these values before starting:

- `APP_PASSWORD`
- `JWT_SECRET`
- `POSTGRES_PASSWORD`
- `DEEPSEEK_API_KEY` if AI chat/search features need DeepSeek
- `DASHSCOPE_API_KEY` if embedding features need DashScope

Do not upload local `.env`, `backend/.env`, or `config.local.json` to the server.

## 5. Copy paper data

From Windows, copy the local knowledge base to the server:

```powershell
scp -r D:\AIworld\mybrain\knowledge_base\* root@YOUR_SERVER_IP:/data/paper-agent/knowledge_base/
```

If `scp` is unstable for many files, use WinSCP and upload this local folder:

```text
D:\AIworld\mybrain\knowledge_base
```

to this remote folder:

```text
/data/paper-agent/knowledge_base
```

You usually do not need to upload `frontend/node_modules`, `frontend/dist`, local `.env` files, or local runtime logs.

## 6. Start

```bash
cd /opt/mybrain/deploy
docker compose up -d --build
docker compose ps
```

Open:

```text
http://YOUR_SERVER_IP
```

Login with:

- username: `APP_USERNAME`
- password: `APP_PASSWORD`

After login, use the app's knowledge-base import action. It reads:

```text
/data/paper-agent/knowledge_base/metadata/library.json
```

and writes paper metadata into Postgres.

## 7. Update from GitHub

After changing code locally, push it to GitHub:

```powershell
cd D:\AIworld\mybrain
git add .
git commit -m "Describe the change"
git push
```

Then update the server:

```bash
cd /opt/mybrain/deploy
bash update-from-github.sh
```

To back up database and paper files before updating:

```bash
cd /opt/mybrain/deploy
DEPLOY_BACKUP=1 bash update-from-github.sh
```

The update script pulls the current branch from GitHub and runs:

```bash
docker compose up -d --build --remove-orphans
```

Your paper data remains in `/data/paper-agent/knowledge_base`; it is not overwritten by GitHub updates.

## 8. Backup

Run this on the server:

```bash
cd /opt/mybrain/deploy
bash backup.sh
```

The backup includes:

- a Postgres SQL dump
- a compressed archive of `/data/paper-agent/knowledge_base`

Backups are written under:

```text
/opt/mybrain/deploy/backups
```

Keep a copy outside the server if the data matters.
