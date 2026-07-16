<div align="center">

<h1>
  <img src="../../assets/Prof_Meerk.png" width="88" alt="Prof. Meerk — Paperfessor 吉祥物" valign="middle"/>
  &nbsp;Paperfessor
</h1>

**输入一个研究方向，输出文献综述、真实实验和一篇符合会议格式的论文。**

*由 Meerk 教授监督 —— 时刻为你的研究站岗放哨。*

[![License: MIT](https://img.shields.io/badge/License-MIT-2E5E4E.svg)](../../LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-33475B.svg)](../../pyproject.toml)

[English](../../README.md) · [简体中文](README.md) · [日本語](../ja/README.md)

<img src="../../assets/Meerk_studio.png" alt="Meerk 教授的工作室：博士智能体负责构思与论文，硕士智能体负责文献评阅，编码智能体负责实验" width="92%"/>

*Meerk 教授的工作室 —— 好奇心 + 知识共享 + 不懈迭代 = 真实成果。*

</div>

---

Paperfessor 是一个运行在你自己电脑、使用你自己 API Key 的三智能体科研助手。
只需给它一个研究方向（一句话即可），三个智能体就会像一个小型课题组一样协作：

| 智能体 | 职责 | 状态查询 API |
|---|---|---|
| 🎓 **博士生** | 提出方法、分派任务、监督进度、撰写并检查论文 | `planning / dispatching / monitoring / reviewing / writing / archiving` |
| 📚 **硕士生** | 广泛文献检索（arXiv + OpenAlex + Scholar）、严谨精读全文、提取证据、调研投稿要求 | `websearch / reading / analyzing / reporting / idle / stopped` |
| 💻 **本科生** | 按严格契约实现方法、下载并预处理真实数据集、跑 k 种子实验 | `coding / thinking / reporting / idle / stopped` |

论文中的每一个数字都是**真实测得的，绝不捏造**：数据集来自真实公开下载
（加载器拒绝合成替身数据）、所提方法通过真实运行验证、每一页渲染结果都
要通过自动排版检查后，这一轮运行才会被接受。

## 安装

```bash
# Python 3.11+
pip install -e ".[gui]"      # 从源码克隆安装
# 或发布后：
pip install paperfessor[gui]
```

建议安装 LaTeX（含 `acmart` 的 TeX Live / MiKTeX）以输出 PDF；没有 LaTeX
时自动回退到 `.docx`（pandoc）或 Markdown。

## 首次配置

API Key 保存在**操作系统钥匙串**（Windows 凭据管理器 / macOS 钥匙串 /
Linux Secret Service）——不落盘、不进日志、不进论文。

```bash
paperfessor key set minimax --key "sk-..."   # 也支持 openai / anthropic / google
paperfessor key test minimax                 # 钥匙串 + LLM 往返测试
paperfessor models list                      # 发现可用模型
```

本地模型同样支持：provider 指向 `ollama` 或 `llamacpp`，无需 Key。

## 跑一篇论文

```bash
paperfessor run "anomaly detection in multivariate time series"
```

`workspace/` 下会得到：

```text
paper/body/paper.pdf      # 会议格式 PDF（acmart 双栏）
paper/body/paper.md       # Markdown 正文源
src/results/results.json  # 实测指标（k = 3 种子，均值 ± 95% CI）
src/figures/              # 结果图、数据样例图、框图
shared/*.md               # 智能体的任务清单与工作日志
archived/<slug>/<run id>/ # 每次尝试的永久档案
```

想用图形界面？运行 `paperfessor-gui`，同样的流水线，外加实时智能体状态、
Token 用量和论文预览。

## 配置

所有设置都可通过 `.env`（前缀 `PAPERFESSOR_`）或 GUI 设置页修改，
完整列表见 [`.env.example`](../../.env.example)。
按智能体选择模型：`paperfessor models pick --group phd`。

## 注意事项

- **诚实是硬性约束。** 综述太薄、模型验证失败、数据集下载失败时，该轮运行
  会如实标记为失败并归档——论文绝不用编造的数字或占位符掩盖缺口。
- **一切可审计。** 博士生的私有备忘（`doc_memo.md`、`article_memo.md`）、
  两份工作日志与归档记录了每个决策及其时间戳。
- **数据集自带许可证信息。** 请遵守上游许可证（例如 NAB 为 AGPL-3.0）。
- **成本参考。** MiniMax-M3 下端到端一轮约消耗 20–25 万输入 Token。

## 负责任使用与免责声明

Paperfessor **仅供科研用途** —— 用于研究多智能体科研工作流，以及辅助
早期草稿。

- **禁止**将其输出直接作为你本人独立完成的成果提交给会议、期刊或课程；
  必须遵守目标场所关于 AI 辅助、署名与抄袭的政策，按要求披露 AI 参与。
- **必须人工核验**所有生成的文字、引用、代码与数字后方可用于任何真实场景。
- **禁止**用于伪造研究、操纵引用、论文工厂或任何违法、欺骗性目的。

**本仓库的作者与贡献者对本软件的任何滥用行为及其一切后果不承担任何责任。**
使用 Paperfessor 即表示接受上述条款以及 [MIT 许可证](../../LICENSE) 的
无担保条款。

## 许可证

[MIT](../../LICENSE)。Meerk 教授吉祥物（`assets/Prof_Meerk.png`）为本仓库
品牌形象的一部分。
