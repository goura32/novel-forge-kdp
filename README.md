# novel-forge-kdp

ローカルLLM（Ollama OpenAI互換API）を使って、小説を「シリーズ > 巻 > 章 > シーン」で企画・設計・執筆・レビュー・改稿するPython製ツールです。

目標は、KDPで商用出版できる品質の小説制作を支援することです。モデル能力による品質限界は残りますが、ツール側では以下を担保します。

- 本文生成の最小単位をシーンに固定
- シリーズごとの作業フォルダ分離
- JSON Schema付きのJSON出力
- LLM入出力RAWログ保存
- Markdownプロンプト管理
- `state.json` による中断・再開
- 各工程のレビュー・改稿
- まず実用最小構成で動かし、段階的に強化

## 実測済みモデル挙動

対象:

- Ollama URL: `http://ws1.local:11434`
- API: `/v1/chat/completions`
- Model: `qwen3.6:35b-a3b-mtp-q4_K_M`
- 想定 context length: `131072`
- 想定 max tokens: `24576`
- ツール側 timeout: `3600s`

設計前に `/tmp/ollama_probe.py` で実測しました。

- JSON出力: `response_format={"type":"json_object"}` と「JSONのみ」指示で、素直なJSONを返す。短いシリーズ企画は `42.18s`、JSON parse成功。
- 長文入力: 約2万字級の設定入力 + 章立てJSON生成は `88.23s`、JSON parse成功。
- 存在しないモデル: HTTP 404、本文は `model 'definitely-missing-model' not found`。
- 短すぎるクライアントtimeout: `TimeoutError`。

設計への反映:

- すべてのLLM呼び出しに1時間timeoutを設定
- HTTPエラー、timeout、JSON parse失敗、Schema検証失敗を明示例外化
- `raw_logs/*.json` にrequest/responseを保存
- JSONがMarkdown code fenceで返った場合だけ安全に剥がす
- Schemaをプロンプト末尾にも添付して、OpenAI互換 `response_format` だけに依存しない
- よくある `{result: ...}` / `{series: ...}` 形式の外側コンテナはSchema検証前に安全にunwrap
- シーン単位で状態保存し、途中失敗しても再開可能にする

## 現在の実装範囲

最小実用構成（MVP）として以下を実装済みです。

- `plan-series`: キーワードからシリーズ企画を生成
- `write-volume`: 1巻分のアウトライン生成、各シーン初稿、レビュー、改稿、Markdown本文出力
- `status`: `state.json` の進捗確認
- `probe-model`: モデル接続・JSON応答確認
- Markdownプロンプト: `src/novel_forge_kdp/prompts/*.md`
- JSON Schema: `src/novel_forge_kdp/schemas/*.json`
- TDDによるコア動作テスト

未実装・次段階:

- 巻全体レビューと巻全体改稿
- 完成済み巻に対する「改稿 or 次巻作成」自動判定
- EPUB/KDP向け整形出力
- 章単位の整合性レビュー
- キャラクター・用語・伏線台帳の自動更新
- 長編向けの要約圧縮・参照範囲制御

## セットアップ

```bash
uv sync
```

Python 3.14 を使用します。

```bash
uv run python --version
```

## 使い方

モデル接続確認:

```bash
uv run novel-forge-kdp probe-model
```

シリーズ企画:

```bash
uv run novel-forge-kdp plan-series "魔法学校 政治陰謀 家族の秘密"
```

生成されたslugを確認して1巻分を作成:

```bash
uv run novel-forge-kdp write-volume <series-slug>
```

進捗確認:

```bash
uv run novel-forge-kdp status <series-slug>
```

作業フォルダは既定で `workspace/<series-slug>/` です。

## 作業フォルダ構造

```text
workspace/<series-slug>/
  state.json
  series_plan.json
  raw_logs/
  volume_001/
    outline.json
    chapters/
      chapter_001/
        scene_001.draft.json
        scene_001.review.json
        scene_001.revised.json
        scene_001.md
```

## 設計方針

- LLM出力は原則JSON。用途別Schemaで検証する。
- 本文はシーン単位で生成し、レビューと改稿を必ず通す。
- プロンプトはMarkdownファイルとして管理し、コード直書きを避ける。
- RAWログは再現性・検証・プロンプト改善の材料として残す。
- `state.json` を各ステップ後に保存し、任意タイミングの中断・再開を可能にする。
- モデルの長時間応答を前提に、timeoutは1時間。
- 暗黙フォールバックより明示エラーを優先する。

## 作業計画と進捗

- [x] GitHub既存リポジトリ名の重複確認
- [x] Python 3.14 + uv プロジェクト作成
- [x] Ollamaモデル実動作検証
- [x] JSON Schema / Markdown prompt 設計
- [x] コア状態管理とワークフロー実装
- [x] TDDテスト追加
- [x] CLI実装
- [x] CLIから実モデルで `probe-model` と `plan-series` を実行確認
- [ ] 巻全体レビュー・次巻作成フロー
- [ ] EPUB/KDP出力
- [ ] 長編品質管理機能

## 開発コマンド

```bash
uv run pytest -q
```
