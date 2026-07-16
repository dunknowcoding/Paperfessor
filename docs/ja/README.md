# Paperfessor

> 研究方向 1 行 → トップ学会/ジャーナル論文草稿 + 実行可能コード、end-to-end。

Paperfessor は 3 智能体デスクトップアプリです。1 文で研究方向を与える
だけで、3 つのエージェントが論文の計画、文献調査、コード作成、実験実
行、原稿執筆、成果物封入までを担当します。

- **博士課程学生** —— 監督者 / 論文アーキテクト
- **修士課程学生** —— 文献調査 + サーベイ
- **学部生** —— コーディング + 実験

## クイックスタート

```bash
# 1. インストール
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[gui,dev]"

# 2. API キーを設定（既定は MiniMax、他 provider も可）
paperfessor key set minimax --key "sk-..."

# 3. 研究方向を与えて実行
paperfessor run "産業 IoT における時系列異常検出のための自己教師あり学習"

# 4. エージェントの成果を確認
cat workspace/paper/body/paper.md
cat workspace/doc_memo.md

# 5. （任意）GUI を起動
paperfessor-gui
```

設定・CLI リファレンス・プロジェクト構成は [メイン README](../../README.md) を参照。
