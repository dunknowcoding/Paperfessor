# Paperfessor

> 一句话研究方向 → 顶会/顶刊论文草稿 + 可运行代码项目，端到端。

Paperfessor 是一个 3 智能体桌面应用。你只需输入一个研究方向（一句
话即可），三个智能体会规划论文、做文献、写代码、跑实验、写正文并
封卷交付。

- **博士生** —— 监督者 / 论文架构师
- **硕士生** —— 文献调研 + 综述
- **本科生** —— 编码 + 实验

## 快速开始

```bash
# 1. 安装
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[gui,dev]"

# 2. 设置 API 密钥（默认 MiniMax，也支持其他 provider）
paperfessor key set minimax --key "sk-..."

# 3. 跑一个研究方向
paperfessor run "面向工业物联网时序异常检测的自监督学习"

# 4. 查看智能体产出的内容
cat workspace/paper/body/paper.md
cat workspace/doc_memo.md

# 5. （可选）启动 GUI
paperfessor-gui
```

完整配置指南、CLI 参考和项目结构请见 [主 README](../../README.md)。
