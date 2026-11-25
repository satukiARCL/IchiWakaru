# IchiWakaru — 整地鯖用整地支援テクスチャ

[たかさわかーる](https://github.com/Helium745/TakasaWakaru)にインスパイアされた、Minecraft Java Edition 1.18〜1.18.2 向けの整地支援リソースパックです。  
![スクショ](screenshots/screenshot.png)  
Screenshot - 青い枠が本テクスチャ（掘る位置・範囲境界が視覚的にわかります）

## 特徴

- 掘り進める位置の床面・天井面および側面（スキル全高を貫通する連続した縦枠）を表示します
  - 折り返し地点でブロックを数えて掘り始める手間を解消します
  - 途中で横にズレても色と交点から簡単に位置復帰できます
- 視認性の高い3色構成を採用しています
  - **青 (`#007FFF`)**: Z軸方向の境界ライン (`y/`)
  - **橙 (`#FF7F00`)**: X軸方向の境界ライン (`x/`)
  - **桃 (`#FF7FED`)**: 2軸の交点 (`dot/`)
- たかさわかーるとの併用も可能です
- 同梱の Python スクリプトにより、代表オフセット版の一括生成だけでなく任意の座標オフセット・カスタムサイズのリソースパックを 1 コマンドで生成できます

## 前提環境

- **Minecraft Java Edition**: 1.18 〜 1.18.2 (`pack_format: 8`)
- **前提 Mod**: [Continuity](https://modrinth.com/mod/continuity)（OptiFine の Connected Textures `method=overlay_repeat` 互換 Mod）
  - 整地鯖向けの前提リソース構成・Continuity が有効であれば動作します

## 対応スキルと収録オフセット

全スキルとも下端 (`side_bottom` / `bottom`)・中間段 (`side_middle`)・上端 (`side_top` / `top`) の 3 ルールを組み合わせ、スキル高さ分の連続した縦長枠を描画します。

| スキル ID | スキル名 | 平面サイズ (`width × depth`) | 縦周期 (`skill_height`) | 対応 Y 範囲 | 収録オフセット `(ox, oz)` |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `tom_bowie_3x3` | トム・ボウイ 3x3（基準版） | `3 × 3` | `3` | `-60 .. 320` | 全9通り: `(0,0)`, `(1,0)`, `(2,0)`, `(0,1)`, `(1,1)`, `(2,1)`, `(0,2)`, `(1,2)`, `(2,2)` |
| `11x11` | 11x11 | `11 × 11` | `11` | `-58 .. 320` | 代表9通り: `(0,0)`, `(1,0)`, `(2,0)`, `(0,1)`, `(0,2)`, `(1,1)`, `(5,0)`, `(0,5)`, `(5,5)` |
| `eternal_vice_15x13` | エターナル・ヴァイス 15x13（エタ版） | `15 × 15` | `13` | `-60 .. 320` | 代表9通り: `(0,0)`, `(1,0)`, `(2,0)`, `(0,1)`, `(0,2)`, `(1,1)`, `(7,0)`, `(0,7)`, `(7,7)` |

> 最後の周期が建築上限 `Y = 320` を超えて途中で切れる場合（例: `11x11` の `Y = 316..320` や `eternal_vice_15x13` の `Y = 317..320`）も、`320` 以下の範囲に含まれる `side_middle` を欠落なく出力しています。

## 導入方法

1. [リリースページ](https://github.com/satukiARCL/IchiWakaru/releases) から以下のいずれかをダウンロードしてください
   - **バンドル ZIP**: `IchiWakaru_tom_bowie_3x3.zip` / `IchiWakaru_11x11.zip` / `IchiWakaru_eternal_vice_15x13.zip` / `IchiWakaru_All.zip`
   - **単体パック ZIP**: `IchiWakaru_<skill>_ox<ox>_oz<oz>.zip`
2. リソースパックフォルダ（`.minecraft/resourcepacks/`）へ配置してください
   - **バンドル ZIP をダウンロードした場合**: バンドル ZIP を解凍し、中に入っている個別の `.zip` ファイル群をそのまま `resourcepacks/` フォルダに入れてください
   - **単体パック ZIP をダウンロードした場合**: 解凍せず、`.zip` ファイルのまま `resourcepacks/` フォルダに入れてください
   - **リポジトリ自体を使う場合**: このリポジトリのルートフォルダ一式をそのまま `resourcepacks/` に入れると、デフォルト基準版（トム・ボウイ 3x3 `ox=0, oz=0`）として機能します
3. オフセットとは前後左右の枠のズレのことです。最初の枠が壁に近すぎるなど整地範囲に合わないときは、Minecraft 内のリソースパック画面からオフセット値 `(ox, oz)` の異なるパックへ切り替えてください（下図参照）

![オフセット1](screenshots/offset1.png)  
オフセット調整例 1

![オフセット2](screenshots/offset2.png)  
オフセット調整例 2

## スクリプトによるビルド・カスタム生成

Python 3.10+ の標準ライブラリのみで動作します（外部パッケージや `.venv` は不要です）。

### 1. 全スキル・全代表オフセットの一括ビルド

```bash
python scripts/build_packs.py
```

実行すると以下が自動生成されます：
- リポジトリ直下の `pack.mcmeta` と `assets/` をデフォルト基準版（`tom_bowie_3x3` / `ox=0, oz=0`）に同期
- `dist/packs/<pack_name>/`: 展開済みリソースパック（全27種）
- `dist/zips/<pack_name>.zip`: 単体導入用 ZIP（ZIP 直下に `pack.mcmeta`, `pack.png`, `assets/`）
- `dist/bundles/IchiWakaru_<skill>.zip` および `dist/bundles/IchiWakaru_All.zip`: 解凍した中身（個別 ZIP 群）をそのまま `resourcepacks/` へ入れられる配布バンドル ZIP

### 2. 任意のオフセット・カスタムスキルの 1 コマンド生成

```bash
# 例: 11x11 のオフセット (ox=3, oz=7) を生成
python scripts/build_packs.py --skill 11x11 --offset-x 3 --offset-z 7

# 例: エターナル・ヴァイス 15x13 で開始高さ Y を +1 段ずらした版を生成
python scripts/build_packs.py --skill eternal_vice_15x13 --offset-x 4 --offset-z 9 --offset-y 1

# 例: 任意サイズのカスタムスキル (平面 7x7, 高さ 5, y_base=-60) を生成
python scripts/build_packs.py --skill custom --width 7 --depth 7 --skill-height 5 --offset-x 2 --offset-z 2
```

カスタム生成はデフォルトで `dist/custom/` に展開フォルダと `.zip` を出力し、リポジトリルート直下のデフォルトパックは変更しません。

| オプション | 説明 | 既定値 |
| :--- | :--- | :--- |
| `--skill` | 元にするスキル（`tom_bowie_3x3`, `11x11`, `eternal_vice_15x13`, `custom`） | なし（全ビルド） |
| `--offset-x` | X 方向のタイルオフセット | `0` |
| `--offset-z` | Z 方向のタイルオフセット | `0` |
| `--offset-y` | 開始高さ Y のオフセット | `0` |
| `--width` | 平面の X 繰り返し幅（`custom` 時は必須） | スキル既定値 |
| `--depth` | 平面の Z 繰り返し奥行（省略時は `--width` と同値） | スキル既定値 |
| `--skill-height` | 縦方向の繰り返し周期（2 以上、`custom` 時は必須） | スキル既定値 |
| `--y-base` | 最初の周期の最下段 Y 座標 | スキル既定値（`custom` は `-60`） |
| `--y-max` | 生成する最大 Y 座標 | `320` |
| `--pack-name` | 出力パック名の上書き | 自動命名 |
| `--output-dir` | カスタム生成の出力先ベースディレクトリ | `dist/custom` |
| `--no-zip` | カスタム生成時に ZIP 作成をスキップ | `false` |
| `--sync-root-only` | ルート直下のデフォルトパック同期のみ実行 | `false` |

### 3. 検証とテストの実行

```bash
python scripts/validate_packs.py
python -m unittest discover -s tests -v
```

## 手動で `.properties` を編集する場合の仕様

本パックは以下のディレクトリ構成で CTM ルールを定義しています（単一のソース設定は [config/packs.json](config/packs.json) と [config/match_blocks.json](config/match_blocks.json) で管理）。

- `assets/minecraft/optifine/ctm/{dot,x,y}/`
  - `top_and_bottom/{bottom,top}.properties`: `faces=bottom` / `faces=top`, `symmetry=opposite`
  - `side_bottom/side_bottom.properties`: `faces=sides`, `symmetry=all`（底辺あり・上端開放）
  - `side_middle/side_middle.properties`: `faces=sides`, `symmetry=all`（上下貫通の縦2本線）
  - `side_top/side_top.properties`: `faces=sides`, `symmetry=all`（上辺あり・下端開放）

編集時のルール：
- `heights`: 負数は必ず括弧付きで記述します（例: `(-60) (-57) ... 0 3 ... 318`）。対象高度範囲は 1.18.2 の `-60 .. 320`（`11x11` は `-58 .. 320`）で、昇順・重複なしにします。
  - `bottom` / `side_bottom` には各周期の最下段、`side_middle` には中間段すべて、`top` / `side_top` には各周期の最上段を指定します。
- `width`, `height`: 平面の繰り返し単位（例: トム・ボウイは `3`、11x11 は `11`、エタ版は `15`）を指定します。
- `tiles`: `width × height` 個のタイル番号（`0`: 透明、`1`: 交点桃、`2`: X軸橙、`3`: Z軸青）を並べます。全 `.properties` ファイルで同一の配置を設定してください。
- `matchBlocks`: Minecraft Java Edition 1.18.2 実在ブロック（固体・装飾ブロック 721 種。空気・流体・技術ブロック・1.19 以降ブロック除外済み）を指定しています。

## ライセンス

CC0 1.0 Universal です。詳細は [LICENSE](LICENSE) をご覧ください。ご自由にどうぞ。
