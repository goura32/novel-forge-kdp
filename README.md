# novel-forge-kdp

ローカルLLM（Ollama OpenAI互換API）を使って、小説を「シリーズ > 巻 > 章 > シーン」で企画・設計・執筆・レビュー・改稿・出力するPython製ツールです。

目標は、KDPで商用出版できる品質の小説制作を支援することです。モデル能力による品質限界は残りますが、ツール側では以下を担保します。

- 本文生成の最小単位をシーンに固定
- シリーズごとの作業フォルダ分離
- JSON Schema付きのJSON出力
- LLM入出力RAWログ保存
- Markdownプロンプト管理
- `state.json` による中断・再開
- シーン、巻、シリーズ台帳のレビュー・改稿
- シリーズ台帳にキャラクターアーク・関係変化・テーマ進行度を記録・更新
- Markdown / text / EPUB のKDP向けドラフト出力
- 完成済み巻なら次巻へ進み、未完了なら再開・改稿する自律継続
- slug安全化、既存シリーズ衝突拒否、atomic write + `.bak` によるデータ保全
- 出版準備判定に基づく品質ゲート（`--force` 指定時のみ強制出力）

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
- シーン単位・巻単位で状態保存し、途中失敗しても再開可能にする
- `state.json` などの重要JSONは一時ファイルに書いてから置換し、直前ファイルを `.bak` として残す
- LLMがHTTP 200で非JSONを返した場合も `LLMClientError` として明示する

## 実装範囲

実装済みCLI:

- `probe-model`: モデル接続・JSON応答確認
- `plan-series`: キーワードからシリーズ企画を生成
- `write-volume`: 1巻分のアウトライン生成、各シーン初稿、レビュー、改稿、シーン/章単位Markdown本文出力
- `complete-volume`: 巻全体レビュー、巻全体改稿、必要に応じた改稿後再レビュー、シリーズ台帳更新、KDP向けドラフト出力。改稿後も出版準備未完了なら停止し、必要な場合のみ `--force` で強制出力
- `continue-series`: 新規/途中なら現巻を完成、完成済みなら次巻を作成
- `export-volume`: 既存原稿からKDP向けファイルを再出力
- `status`: `state.json` の進捗確認

実装済み設計要素:

- Markdownプロンプト: `src/novel_forge_kdp/prompts/*.md`
- JSON Schema: `src/novel_forge_kdp/schemas/*.json`
- RAWログ: `raw_logs/*.json`
- シリーズ台帳: `bible.json`
- KDP向け出力: `exports/manuscript.md`, `exports/kdp.txt`, `exports/book.epub`, `exports/metadata.json`
- TDDによるコア動作テスト

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

生成されたslugを確認して1巻分をシーン単位で作成:

```bash
uv run novel-forge-kdp write-volume <series-slug>
```

巻全体レビュー、巻全体改稿、台帳更新、KDP向けドラフト出力:

```bash
uv run novel-forge-kdp complete-volume <series-slug>
```

レビューが出版準備未完了でも検証用に出力したい場合:

```bash
uv run novel-forge-kdp complete-volume <series-slug> --force
```

自律継続。未完了なら再開・完成、完成済みなら次巻作成:

```bash
uv run novel-forge-kdp continue-series <series-slug>
```

KDP向け出力だけ再生成:

```bash
uv run novel-forge-kdp export-volume <series-slug>
```

実モデルのスモーク検証などで1シーンだけ処理する場合:

```bash
uv run novel-forge-kdp write-volume <series-slug> --max-scenes 1
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
  state.json.bak
  series_plan.json
  bible.json
  raw_logs/
  volume_001/
    outline.json
    volume_review.json
    volume_revised.json
    volume_revised.md
    chapters/
      chapter_001/
        scene_001.draft.json
        scene_001.review.json
        scene_001.revised.json
        scene_001.md
        chapter.md
    exports/
      manuscript.md
      kdp.txt
      book.epub
      metadata.json
      chapters/
        chapter_001.md
```

## 設計方針

- LLM出力は原則JSON。用途別Schemaで検証する。
- 本文はシーン単位で生成し、レビューと改稿を必ず通す。各シーンをまとめた `chapters/chapter_NNN/chapter.md` と、巻改稿後の最終原稿から切り出した `exports/chapters/chapter_NNN.md` も保存し、人間が章単位で読めるようにする。
- 巻全体でもレビューと改稿を行い、単発シーンの寄せ集めで終わらせない。
- プロンプトはMarkdownファイルとして管理し、コード直書きを避ける。
- RAWログは再現性・検証・プロンプト改善の材料として残す。未公開原稿とプロットが平文保存されるため、共有・公開・バックアップ時は取り扱いに注意する。
- `state.json` を各ステップ後にatomic writeし、直前ファイルを `.bak` として保存する。
- `bible.json` でキャラクター、用語、伏線、継続性メモを蓄積する。
- 出版準備判定がfalseの巻は、まず巻全体改稿と改稿後再レビューを行う。改稿後もfalseなら標準では停止し、`--force` 指定時のみ出力する。
- EPUBはKDP向け確認用のドラフトとして生成する。商用品質の最終EPUBには別途epubcheckや表紙・CSS・詳細メタデータ調整を行う。
- モデルの長時間応答を前提に、timeoutは1時間。
- 暗黙フォールバックより明示エラーを優先する。

## 作業計画と進捗

- [x] GitHub既存リポジトリ名の重複確認
- [x] Python 3.14 + uv プロジェクト作成
- [x] Ollamaモデル実動作検証
- [x] JSON Schema / Markdown prompt 設計
- [x] コア状態管理とワークフロー実装
- [x] シーン単位の初稿・レビュー・改稿
- [x] 巻全体レビュー・巻全体改稿
- [x] 完成済み巻に対する次巻作成フロー
- [x] キャラクター・用語・伏線台帳の自動更新
- [x] Markdown / text / EPUB のKDP向けドラフト出力
- [x] slug安全化・パストラバーサル拒否・既存シリーズ上書き拒否
- [x] atomic write + `.bak` による状態ファイル保護
- [x] 不完全原稿の黙殺禁止とLLM非JSON応答の明示例外化
- [x] 出版準備判定に基づく品質ゲート
- [x] Schema制約強化と異常系テスト追加
- [x] CLI実装
- [x] TDDテスト追加
- [x] CLIから実モデルで `probe-model` / `plan-series` / `write-volume --max-scenes 1` を実行確認

## 開発コマンド

```bash
uv run pytest -q
uv build
```
