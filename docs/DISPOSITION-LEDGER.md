# 仕様・要件判断台帳 (Disposition Ledger)

本ドキュメントは、IchiWakaru リポジトリにおける各機能要件の実装ステータス、出自区分（Provenance）、および処遇判断（Disposition）の根拠を追跡・記録します。

## ステータス定義 (Disposition Statuses)
- **`Complete`**: 完全実装済み。対応する受入ゲート（Acceptance Gate）を通過している。
- **`Partial`**: 制限付き・一部実装済み。制約事項や前提条件が存在する。
- **`Deferred`**: 今回のスコープ外として後回し・保留。または自動化環境外のゲート（実機確認等）に委ねられた項目。
- **`Policy-Denied`**: アーキテクチャ方針、技術制約、または互換性境界に基づき、**意図的に実装しないことを決定**した項目。

## 出自区分 (Provenance Categories)
- **`Human-Specified`**: ユーザー（Director）が明示的に確定・指定した仕様および制約（A1〜A5）。
- **`Agent-Proposed`**: エージェントが設計案・実装構成として提示し採用された項目。
- **`Collaboratively Refined`**: ユーザー確認事項と既存実装の解析を組み合わせて精査・洗練した項目。
- **`Test-Driven Correction`**: 実ファイル・既存 `HEAD` 差分・データの検証から判明した不備を修正した項目。

---

## 要件・機能判断一覧 (Feature Disposition Ledger)

| 要件 / 機能項目 | ステータス | 出自 (Provenance) | 対応受入ゲート | 処遇判断の理由・技術根拠 (Disposition Rationale) | 参照ファイル |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Python 標準ライブラリのみによるビルド・検証基盤 (A1) | `Complete` | `Human-Specified` / `Agent-Proposed` | Gate 1, Gate 3 | 外部依存（Pillow 等）や `.venv` を不要とし、標準ライブラリ (`zlib`, `struct`, `zipfile`, `json`) のみで決定論的に PNG/CTM/ZIP を生成・検証可能にした。 | [build_packs.py](../scripts/build_packs.py), [pack_core.py](../scripts/pack_core.py) |
| デフォルト基準パックのルート自動同期 (`tom_bowie_3x3` `ox=0, oz=0`) (A1) | `Complete` | `Human-Specified` | Gate 1, Gate 2 | リポジトリ直下の `pack.mcmeta` と `assets/` をデフォルト基準版とバイト単位で一致させ、リポジトリ単体導入とスクリプトビルドの両立を保証した。 | [packs.json](../config/packs.json), [validate_packs.py](../scripts/validate_packs.py) |
| 全高連続枠 `side_middle` 新設（PNG + `.properties`） (A2) | `Complete` | `Human-Specified` / `Collaboratively Refined` | Gate 2, Gate 3 | `side_bottom` / `side_top` と同じく `faces=sides` + `symmetry=all` 構成を採用。全側面が `(X, Z)` 座標で統一判定される Continuity/OptiFine 仕様（`screenshots/offset1.png`・`screenshot.png` で実証済み）に合わせ、縦2本線 (`x=1, x=14`, `y=0..15`) の 16×16 RGBA PNG を 3 色（桃 `(255,127,237)`, 橙 `(255,127,0)`, 青 `(0,127,255)`）で自動生成し、既存 `side_bottom` / `side_top` と隙間なく連結させた。 | [pack_core.py](../scripts/pack_core.py) |
| 3スキル寸法定義と上限 `320` 未完周期対応 (A2) | `Complete` | `Human-Specified` / `Collaboratively Refined` | Gate 2, Gate 3 | `tom_bowie_3x3` (`3x3x3`, `y=-60..320`)、`11x11` (`11x11x11`, `y=-58..320`)、`eternal_vice_15x13` (`15x15x13`, `y=-60..320`) を数式生成。最後の未完周期で最上段が `320` を超える場合も `y <= 320` の `side_middle` を含め、`bottom ∪ middle ∪ top == [y_base, 320]` の厳密分割を実現。 | [packs.json](../config/packs.json), [pack_core.py](../scripts/pack_core.py) |
| `HEAD` 版 `11x11` (`x/side_bottom`) タイポ修正 (A2) | `Complete` | `Test-Driven Correction` | Gate 2, Gate 3 | `HEAD` 時の `x/side_bottom/side_bottom.properties` に残存していた手打ちミス (`20`, `205`, `216`) を数式生成によって根絶し、全ファイルの `heights` 公差・昇順・重複なし・負数括弧 `(-n)` フォーマットを保証した。 | [pack_core.py](../scripts/pack_core.py), [validate_packs.py](../scripts/validate_packs.py) |
| オフセットバリエーション収録＆配布 ZIP/バンドル構造 (A3) | `Complete` | `Human-Specified` / `Collaboratively Refined` | Gate 1, Gate 2, Gate 3 | `tom_bowie_3x3` は全9通り `(0..2, 0..2)`、`11x11` と `eternal_vice_15x13` は基準・近傍・中央系を含む各代表9通りを `config/packs.json` に定義し全27パックを生成。単体 ZIP (`dist/zips/`) 直下に `pack.mcmeta` / `pack.png` / `assets/` を配置し、バンドル ZIP (`dist/bundles/IchiWakaru_<skill>.zip`, `IchiWakaru_All.zip`) 直下に個別パック ZIP をフラット格納することで、解凍した中身をそのまま `resourcepacks/` へ配置できるようにした。 | [packs.json](../config/packs.json), [build_packs.py](../scripts/build_packs.py) |
| CLI による任意オフセット・カスタムスキル生成 (A3) | `Complete` | `Human-Specified` | Gate 1, Gate 3 | `--skill`, `--offset-x`, `--offset-z`, `--offset-y`, `--width`, `--depth`, `--skill-height`, `--y-base`, `--y-max`, `--output-dir` により 1 コマンドで任意のカスタムパックを生成可能にした（カスタム実行時はルート直下を上書きしない安全分離設計）。 | [build_packs.py](../scripts/build_packs.py) |
| MC 1.18.2 (`pack_format: 8`) `matchBlocks` 一元化と精査 (A4) | `Complete` | `Human-Specified` / `Collaboratively Refined` | Gate 2, Gate 3 | 12ファイルに重複していた 536 ブロックを `config/match_blocks.json` に一元化。PrismarineJS `minecraft-data` (`data/pc/1.18/blocks.json`、1.18/1.18.1/1.18.2 共通 898 ブロック) および Minecraft Wiki の 1.18.1/1.18.2 変更履歴を照合し、非固体・不可視・流体・技術ブロック・草花・珊瑚ファン・レール等 177 種を除外、欠落していた階段(48)・フェンス(9)・フェンスゲート(8)・ドア(9)・トラップドア(9)・ボタン(10)・感圧板(12)・色付きガラス(16)・板ガラス(16)・シュルカーボックス(17)・カーペット(17)・頭蓋骨・鍾乳石・キャンドル類等を補完して計 721 ブロックへ再編成した。 | [match_blocks.json](../config/match_blocks.json) |
| ドキュメント・URL統一・`.gitignore`・BOMなしUTF-8統一 (A5) | `Complete` | `Human-Specified` | Gate 2 | `README.md` のリリース URL を `https://github.com/satukiARCL/IchiWakaru/releases` に更新し `# TODO` を解消。`.gitignore` 整備と全テキストの UTF-8 (BOMなし)・LF・末尾改行統一を検証済み。 | [README.md](../README.md), [.gitignore](../.gitignore) |
| Minecraft Java Edition 1.18.2 + Continuity 実機描画確認 | `Deferred` | `Human-Specified` / `Agent-Proposed` | Gate 4 | 本開発環境はヘッドレス環境であり Minecraft Java Edition クライアントおよび Continuity Mod の実機実行環境が存在しないため、実機描画テスト自体は開発環境外（ユーザー側最終確認）とした。代わりに `screenshots/offset1.png`・`screenshot.png` の実機挙動と CTM 仕様に基づくピクセル座標・`heights` 分割・`tiles` 配置・ZIP 階層の完全自動検証を実施済み。 | [validate_packs.py](../scripts/validate_packs.py) |
| サードパーティ製画像処理ライブラリ（Pillow 等）の導入 | `Policy-Denied` | `Human-Specified` | - | 「Python 標準ライブラリのみで完結し `.venv` 不要とする」構成方針（A1）に反するため導入しない。16×16 RGBA PNG のエンコード/デコードは標準ライブラリ `zlib` + `struct` で実装済み。 | [pack_core.py](../scripts/pack_core.py) |
| Minecraft 1.19 以降の新規ブロック ID の収録 | `Policy-Denied` | `Human-Specified` | Gate 2, Gate 3 | 対象バージョンが Minecraft Java Edition 1.18〜1.18.2 (`pack_format: 8`) であるため、`mud`, `mangrove_*`, `sculk_catalyst`, `reinforced_deepslate`, `cherry_*` 等の 1.19 以降ブロック ID は検証ブラックリストにより意図的に拒否・除外している。 | [match_blocks.json](../config/match_blocks.json), [validate_packs.py](../scripts/validate_packs.py) |
| 未検証ブロック ID の推測による追加 | `Policy-Denied` | `Human-Specified` | Gate 2, Gate 3 | 存在しないブロック ID 混入によるパック不具合を防止するため、`minecraft-data` 1.18.2 全量データと照合された ID のみを収録する方針を厳守。 | [match_blocks.json](../config/match_blocks.json) |
| `command_block` / `structure_block` / `barrier` / 流体 / 空気系ブロックへの枠描画 | `Policy-Denied` | `Human-Specified` / `Collaboratively Refined` | Gate 2, Gate 3 | 不可視ブロック・技術ブロック・流体・ポータルへの枠表示は視認性を損ない意図しない描画を引き起こすため除外した。なお、雪原・山岳整地で実体のある立方体ブロックとして扱われる `powder_snow` は整地実用性を考慮して収録対象に含めた。 | [match_blocks.json](../config/match_blocks.json) |

---

## ゲート通過エビデンス (Gate Evidence Summary)
- **Gate 1 (ビルド・ZIP・バンドル生成)**: `python scripts/build_packs.py` によるルート同期＋全27パック・ZIP・4バンドル生成と CLI カスタム生成の正常完了（実測コマンド実行ログ参照）。
- **Gate 2 (静的整合性・エンコーディング・数式・RGBA 検証)**: `python scripts/validate_packs.py` による BOM ゼロ・JSON 構文・`matchBlocks` 整合・`tiles` 検証・`heights` 分割・16×16 RGBA ピクセル検証・ルート/ZIP/バンドル一致の全項目パス。
- **Gate 3 (自動単体・統合テスト)**: `python -m unittest discover -s tests -v` による全ユニットテスト・統合テストの全件パス。
- **Gate 4 (Minecraft 1.18.2 + Continuity 実機描画確認)**: 開発環境外（`Deferred` — 実機環境にてリリース ZIP を導入し確認予定）。
