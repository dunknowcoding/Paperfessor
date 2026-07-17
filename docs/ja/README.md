<div align="center">

<h1>
  <img src="../../assets/Prof_Meerk.png" width="88" alt="Prof. Meerk — Paperfessor のマスコット" valign="middle"/>
  &nbsp;Paperfessor
</h1>

**研究方向を 1 行入力すると、サーベイ・実実験・学会フォーマットの論文が出てくる。**

*Meerk 教授が監修 — あなたの研究をいつでも見守っています。*

[![License: MIT](https://img.shields.io/badge/License-MIT-2E5E4E.svg)](../../LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-33475B.svg)](../../pyproject.toml)

[English](../../README.md) · [简体中文](../zh-CN/README.md) · **日本語** · [Español](../es/README.md) · [Français](../fr/README.md) · [Deutsch](../de/README.md) · [Italiano](../it/README.md) · [Português](../pt/README.md) · [Русский](../ru/README.md) · [한국어](../ko/README.md) · [العربية](../ar/README.md)

<img src="../../assets/Meerk_studio.png" alt="Meerk 教授のスタジオ：PhD エージェントが構想と論文、Master エージェントが文献レビュー、コーダーエージェントが実験を担当" width="92%"/>

*Meerk 教授のスタジオ — 好奇心 + 知識の共有 + 絶え間ない反復 = 本物のインパクト。*

</div>

---

Paperfessor は、あなた自身のマシンとあなた自身の API キーで動く
3 エージェント型リサーチアシスタントです。研究方向（1 文で十分）を
与えると、小さな研究室のように協働します：

| エージェント | 役割 | ステータス API |
|---|---|---|
| 🎓 **博士課程学生** | 手法の考案、タスク割当、監督、論文の執筆と検査 | `planning / dispatching / monitoring / reviewing / writing / archiving` |
| 📚 **修士課程学生** | 広範な文献検索（arXiv + OpenAlex + Scholar）、全文精読、エビデンス抽出、投稿要件調査 | `websearch / reading / analyzing / reporting / idle / stopped` |
| 💻 **学部生** | 厳格な契約に沿った実装、実データセットの取得と前処理、k シード実験 | `coding / thinking / reporting / idle / stopped` |

論文中のすべての数値は**実測値であり、決して捏造されません**。
データセットは実在の公開データのみ（合成の代替データはロード段階で拒否）、
提案手法は実際に実行して検証され、レンダリングされた各ページは自動レイアウト
検査に合格して初めてそのランが受理されます。

## インストール

```bash
# Python 3.11+
pip install -e ".[gui]"      # クローンから
# 公開後は：
pip install paperfessor[gui]
```

PDF 出力には LaTeX（`acmart` を含む TeX Live / MiKTeX）を推奨。無い場合は
`.docx`（pandoc）または Markdown にフォールバックします。

## 初期設定

API キーは **OS のキーチェーン**（Windows 資格情報マネージャー / macOS
キーチェーン / Linux Secret Service）に保存され、ディスク・ログ・論文には
一切残りません。

```bash
paperfessor key set minimax --key "sk-..."   # openai / anthropic / google も可
paperfessor key test minimax                 # キーチェーン + LLM の往復テスト
paperfessor models list                      # 利用可能モデルの検出
```

ローカルモデルも利用可能：provider を `ollama` / `llamacpp` に向ければ
キー不要です。

## 論文を 1 本走らせる

```bash
paperfessor run "anomaly detection in multivariate time series"
```

`workspace/` に得られるもの：

```text
paper/body/paper.pdf      # 学会フォーマット PDF（acmart 2 段組）
paper/body/paper.md       # Markdown ソース
src/results/results.json  # 実測メトリクス（k = 3 シード、平均 ± 95% CI）
src/figures/              # 結果チャート、データサンプル図、ブロック図
shared/*.md               # エージェントのガイドと作業ログ
archived/<slug>/<run id>/ # 各試行の永久アーカイブ
```

GUI 派には `paperfessor-gui`。同じパイプラインに、エージェントの
リアルタイムステータス、トークン使用量、論文プレビューが付きます。

## 設定

すべて `.env`（接頭辞 `PAPERFESSOR_`）または GUI の設定タブから変更可能。
全項目は [`.env.example`](../../.env.example) を参照。エージェント別の
モデル選択：`paperfessor models pick --group phd`。

## 知っておくべきこと

- **誠実さは仕様です。** サーベイが薄い・モデル検証が失敗・データセットが
  取得不能なら、そのランは正直に「失敗」と記録されアーカイブされます。
  論文が捏造した数値やプレースホルダで欠落を隠すことはありません。
- **すべて監査可能。** 博士のメモ（`doc_memo.md`、`article_memo.md`）、
  2 つの作業ログ、アーカイブに全決定がタイムスタンプ付きで残ります。
- **データセットにはライセンス情報が付属。** 上流ライセンス（例：NAB は
  AGPL-3.0）を遵守してください。
- **コスト目安。** MiniMax-M3 でエンドツーエンド 1 ランあたり入力
  約 20–25 万トークン。

## 責任ある利用と免責事項

Paperfessor は**研究目的専用**です — マルチエージェント科学ワークフローの
研究、および初期草稿の補助のために作られています。

- 出力を自分の単独成果として学会・ジャーナル・授業に提出しては
  **いけません**。投稿先の AI 利用・著者資格・剽窃ポリシーに必ず従い、
  要求される場合は AI の関与を開示してください。
- 生成されたテキスト・引用・コード・数値は、実利用の前に**必ず人間が
  検証**してください。
- 研究の捏造、引用操作、ペーパーミル、その他違法・欺瞞的な目的への利用は
  **禁止**です。

**本リポジトリの作者および貢献者は、本ソフトウェアのいかなる誤用にも、
その利用から生じるいかなる結果にも、一切の責任を負いません。**
Paperfessor の利用は、上記条件と [MIT ライセンス](../../LICENSE) の
無保証条項への同意を意味します。

## ライセンス

[MIT](../../LICENSE)。Meerk 教授のマスコット（`assets/Prof_Meerk.png`）は
本リポジトリのブランディングの一部です。
