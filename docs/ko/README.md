<div align="center">

<h1>
  <img src="../../assets/Prof_Meerk.png" width="88" alt="Meerk 교수 — Paperfessor 마스코트" valign="middle"/>
  &nbsp;Paperfessor
</h1>

**연구 방향 한 줄을 넣으면, 문헌 조사·실제 실험·학회 서식의 논문이 나옵니다.**

[![License: MIT](https://img.shields.io/badge/License-MIT-2E5E4E.svg)](../../LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-33475B.svg)](../../pyproject.toml)

[English](../../README.md) · [简体中文](../zh-CN/README.md) · [日本語](../ja/README.md) · [Español](../es/README.md) · [Français](../fr/README.md) · [Deutsch](../de/README.md) · [Italiano](../it/README.md) · [Português](../pt/README.md) · [Русский](../ru/README.md) · **한국어** · [العربية](../ar/README.md)

<img src="../../assets/Meerk_studio.png" alt="Meerk 교수의 스튜디오: 박사과정 에이전트가 아이디어와 논문을, 석사과정 에이전트가 문헌 검토를, 코더 에이전트가 실험을 담당" width="92%"/>

*Meerk 교수의 스튜디오 — 호기심 + 지식 공유 + 끈질긴 반복 = 진짜 성과.*

</div>

---

Paperfessor는 당신의 컴퓨터에서 당신의 API 키로 동작하는 3-에이전트 연구
어시스턴트입니다. 연구 방향(한 문장이면 충분)을 주면, 에이전트들이 작은
연구실처럼 협업합니다:

| 에이전트 | 역할 | 상태 API |
|---|---|---|
| 🎓 **박사과정** | 방법 고안, 작업 배분, 감독, 논문 집필·검사 | `planning / dispatching / monitoring / reviewing / writing / archiving` |
| 📚 **석사과정** | 광범위 문헌 검색(arXiv + OpenAlex + Scholar), 전문 정독, 근거 추출 | `websearch / reading / analyzing / reporting / idle / stopped` |
| 💻 **학부생** | 엄격한 계약에 따른 구현, 실제 데이터셋 다운로드·전처리, k-시드 실험 수행 | `coding / thinking / reporting / idle / stopped` |

논문의 모든 숫자는 **측정된 값이며 절대 지어내지 않습니다**: 데이터셋은
실제 공개 다운로드(로더가 합성 대체 데이터를 거부), 제안 방법은 실제 실행으로
검증되고, PDF의 모든 페이지는 자동 레이아웃 검사를 통과해야 실행이
승인됩니다.

## 설치

```bash
# Python 3.11+
pip install -e ".[gui]"        # 클론에서
# 배포 후에는:
pip install paperfessor[gui]
```

PDF 출력을 위해 LaTeX(TeX Live/MiKTeX, `acmart` 포함)를 권장합니다. 없으면
`.docx`(pandoc) 또는 Markdown으로 대체됩니다.

## 초기 설정

API 키는 **운영체제 키체인**에 저장됩니다 — 디스크에도, 로그에도, 논문에도
남지 않습니다.

```bash
paperfessor key set minimax --key "sk-..."   # openai / anthropic / google 도 지원
paperfessor key test minimax                 # 왕복 테스트
paperfessor models list                      # 사용 가능한 모델
```

## 논문 생성

```bash
paperfessor run "anomaly detection in multivariate time series"
```

`workspace/`의 산출물: `paper/body/paper.pdf`(학회 서식 PDF),
`src/results/results.json`(측정 지표, k = 3 시드, 평균 ± 95% CI), 실제
그림들, 에이전트 작업 로그. GUI가 좋다면 `paperfessor-gui`.

## 책임 있는 사용과 면책 조항

Paperfessor는 **연구 목적 전용**으로 만들어졌습니다.

- 산출물을 본인의 단독 성과로 학회·저널·수업에 제출하지 **마세요**. 대상
  기관의 AI 지원·저자·표절 정책을 준수하고, 요구되는 경우 AI 지원 사실을
  공개하세요.
- **모든 것을 검증하세요.** 생성된 텍스트·인용·코드·수치는 실제 사용 전에
  반드시 사람이 확인해야 합니다.
- 연구 조작, 인용 조작, 논문 공장 등 불법적이거나 기만적인 목적에 사용하지
  **마세요**.

**이 저장소의 작성자와 기여자는 이 소프트웨어의 오용 및 사용으로 인한 어떤
결과에 대해서도 책임지지 않습니다.**

## 라이선스

[MIT](../../LICENSE). Meerk 교수 마스코트는 이 저장소 브랜딩의 일부입니다.
