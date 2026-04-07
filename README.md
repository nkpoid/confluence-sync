# confluence-sync

Confluence Data Center のページを Markdown 形式でローカルにエクスポートし、差分更新できる CLI ツール。

## セットアップ

[uv](https://docs.astral.sh/uv/) が必要です。

```bash
uv sync
```

## 環境変数

```bash
export CONFLUENCE_BASE_URL='https://confluence.your-company.com'
export CONFLUENCE_PAT='your-token'
```

| 変数 | 必須 | 説明 |
|------|------|------|
| `CONFLUENCE_BASE_URL` | ※ | Confluence のベース URL。設定ファイルの `base_url` より優先 |
| `CONFLUENCE_PAT` | Yes | Personal Access Token (Bearer 認証) |

※ 環境変数か設定ファイルのいずれかで指定が必要

PAT の作成手順: Confluence 右上のプロフィールアイコン → **Personal Access Tokens** → **Create token**

## 設定ファイルの作成

対話形式で `.confluence-sync.toml` を生成します。

```bash
uv run confluence-sync init
```

生成される設定ファイルの例:

```toml
# base_url は環境変数 CONFLUENCE_BASE_URL でも指定可（環境変数が優先）
base_url = "https://confluence.your-company.com"

output_dir = "./confluence-export"
spaces = ["DEV", "OPS"]  # 空配列なら全スペース対象

[sync]
include_attachments = true
attachment_dir = "_attachments"
```

## 使い方

```bash
# 差分同期（初回は全件取得）
uv run confluence-sync pull

# 強制全件取得
uv run confluence-sync pull --full

# 削除されたページも検知（.trash/ に移動）
uv run confluence-sync pull --detect-deletes

# 前回同期からの変更件数を確認
uv run confluence-sync status

# アクセス可能なスペース一覧
uv run confluence-sync list-spaces
```

## 出力ディレクトリ構成

Confluence のページ階層がそのままディレクトリ構造に反映されます。

```
confluence-export/
├── DEV/
│   ├── _attachments/
│   │   └── 12345/
│   │       └── diagram.png
│   ├── 10000-getting-started.md
│   ├── 10001-architecture/          ← 子ページを持つページはディレクトリも作成
│   │   ├── 12345-api-design.md
│   │   └── 12346-database/
│   │       └── 67890-schema.md
│   └── 10001-architecture.md
├── OPS/
│   └── ...
└── .sync-state.json
```

各 Markdown ファイルには YAML frontmatter が付与されます。

```markdown
---
id: "12345"
title: "ページタイトル"
space: "DEV"
url: "https://confluence.your-company.com/spaces/DEV/pages/12345"
version: 42
last_modified: "2025-04-01T10:30:00Z"
labels: ["api", "design"]
---

# ページタイトル

本文...
```

## 開発

```bash
# テスト実行
uv run pytest tests/ -v
```
