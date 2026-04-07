# confluence-sync

Confluence Data Center のページを Markdown 形式でローカルにエクスポートし、差分更新できる CLI ツール。

## セットアップ

[uv](https://docs.astral.sh/uv/) が必要です。

```bash
uv sync
```

## 認証

Confluence Data Center の Personal Access Token (PAT) を環境変数に設定します。

```bash
export CONFLUENCE_PAT='your-token'
```

PAT の作成手順: Confluence 右上のプロフィールアイコン → **Personal Access Tokens** → **Create token**

## 設定ファイルの作成

対話形式で `.confluence-sync.toml` を生成します。

```bash
uv run confluence-sync init
```

生成される設定ファイルの例:

```toml
base_url = "https://confluence.your-company.com"
# PAT は環境変数 CONFLUENCE_PAT から読み取り（ファイルには書かない）

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

```
confluence-export/
├── DEV/
│   ├── _attachments/
│   │   └── 12345/
│   │       └── diagram.png
│   ├── 12345-page-title.md
│   └── 67890-another-page.md
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
