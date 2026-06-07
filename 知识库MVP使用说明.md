# 3DGS 自生长知识库 MVP 使用说明

当前项目已经改为“网站程序 + 独立知识库目录”的结构。代码仓库不再作为笔记库使用；论文元数据、PDF、Markdown 笔记、报告和缓存放在 `KNOWLEDGE_BASE_DIR` 指向的目录。

## 推荐目录

```text
knowledge_base/
├─ papers/
│  ├─ pdf/
│  └─ notes/
├─ indexes/
├─ reports/
├─ assets/
│  └─ figures/
├─ cache/
│  ├─ pdf_text/
│  └─ mineru/
└─ metadata/
   └─ library.json
```

## 迁移命令

只检查，不写文件：

```powershell
python Scripts/migrate_knowledge_base.py --target D:\AIworld\paper-agent\knowledge_base
```

执行迁移：

```powershell
python Scripts/migrate_knowledge_base.py --target D:\AIworld\paper-agent\knowledge_base --apply
```

默认策略：

- 迁移 `data/library.json` 到 `metadata/library.json`。
- 把旧 `note_path` 统一改成 `papers/notes/*.md`。
- 复制索引、报告、图片和 PDF 缓存。
- 不复制旧精读笔记正文，后续由网站重新生成。
- 不复制 MinerU 缓存，后续按需重新解析。

## 网站导入

1. 设置后端环境变量 `KNOWLEDGE_BASE_DIR`。
2. 启动后端和前端。
3. 登录网站后点击“导入知识库”。
4. 导入后，Postgres 保存论文标题、作者、年份、会议、标签、阅读状态、笔记路径和检索数据。

## 注意

旧的 `Scripts/kb.py` 仍可作为本地辅助脚本使用，但主流程以网站和 Postgres 为准。后续如果继续扩展 CLI，再把它完全改成新的小写目录结构。
