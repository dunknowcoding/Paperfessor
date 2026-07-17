<div align="center">

<h1>
  <img src="../../assets/Prof_Meerk.png" width="88" alt="Prof. Meerk — o mascote do Paperfessor" valign="middle"/>
  &nbsp;Paperfessor
</h1>

**Entra uma direção de pesquisa. Saem uma revisão da literatura, experimentos reais e um artigo formatado para conferência.**

[![License: MIT](https://img.shields.io/badge/License-MIT-2E5E4E.svg)](../../LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-33475B.svg)](../../pyproject.toml)

[English](../../README.md) · [简体中文](../zh-CN/README.md) · [日本語](../ja/README.md) · [Español](../es/README.md) · [Français](../fr/README.md) · [Deutsch](../de/README.md) · [Italiano](../it/README.md) · **Português** · [Русский](../ru/README.md) · [한국어](../ko/README.md) · [العربية](../ar/README.md)

<img src="../../assets/Meerk_studio.png" alt="O estúdio do Prof. Meerk: o agente doutorando cria ideias e o artigo, o agente mestrando revisa a literatura, o agente programador executa os experimentos" width="92%"/>

*Dentro do estúdio do Prof. Meerk — mentes curiosas + conhecimento compartilhado + iteração incansável = impacto real.*

</div>

---

O Paperfessor é um assistente de pesquisa com três agentes que roda na sua
própria máquina com a sua própria chave de API. Dê a ele uma direção de
pesquisa (uma frase basta) e o grupo de agentes trabalha como um pequeno
laboratório:

| Agente | Papel | API de status |
|---|---|---|
| 🎓 **Doutorando** | Inventa o método, distribui tarefas, supervisiona, escreve e inspeciona o artigo | `planning / dispatching / monitoring / reviewing / writing / archiving` |
| 📚 **Mestrando** | Busca bibliográfica ampla (arXiv + OpenAlex + Scholar), leitura integral rigorosa, extração de evidências | `websearch / reading / analyzing / reporting / idle / stopped` |
| 💻 **Graduando** | Implementa o método sob contrato estrito, baixa e pré-processa dados reais, roda experimentos com k sementes | `coding / thinking / reporting / idle / stopped` |

Todo número no artigo é **medido, nunca inventado**: os conjuntos de dados
são downloads públicos reais (os loaders recusam dados sintéticos), o método
proposto é verificado por execução real e cada página do PDF passa por uma
inspeção automática de layout antes de a execução ser aceita.

## Instalação

```bash
# Python 3.11+
pip install -e ".[gui]"        # a partir de um clone
# ou, depois de publicado:
pip install paperfessor[gui]
```

Recomenda-se LaTeX (TeX Live/MiKTeX com `acmart`) para o PDF; sem ele, há
retorno para `.docx` (pandoc) ou Markdown.

## Primeira configuração

As chaves de API ficam no **chaveiro do sistema operacional** — nunca em
disco, nem em logs, nem no artigo.

```bash
paperfessor key set minimax --key "sk-..."   # também openai / anthropic / google
paperfessor key test minimax                 # teste de ida e volta
paperfessor models list                      # modelos disponíveis
```

## Gerar um artigo

```bash
paperfessor run "anomaly detection in multivariate time series"
```

Resultados em `workspace/`: `paper/body/paper.pdf` (PDF em formato de
conferência), `src/results/results.json` (métricas medidas, k = 3 sementes,
média ± IC de 95%), figuras reais e os registros de trabalho dos agentes.
Prefere uma janela? `paperfessor-gui`.

## Uso responsável e isenção de responsabilidade

O Paperfessor foi construído **apenas para fins de pesquisa**.

- **Não** submeta a saída dele como trabalho próprio sem assistência a
  conferências, periódicos ou cursos; siga as políticas do destino sobre
  assistência de IA, autoria e plágio, e declare a assistência de IA quando
  exigido.
- **Verifique tudo.** Textos, citações, código e números gerados devem ser
  conferidos por uma pessoa antes de qualquer uso real.
- **Não** use para pesquisa fabricada, manipulação de citações, fábricas de
  artigos nem qualquer finalidade ilegal ou enganosa.

**Os autores e colaboradores deste repositório não aceitam nenhuma
responsabilidade pelo mau uso deste software nem pelas consequências do seu
uso.**

## Licença

[MIT](../../LICENSE). O mascote Prof. Meerk faz parte da identidade do
repositório.
