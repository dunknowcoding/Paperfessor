<div align="center">

<h1>
  <img src="../../assets/Prof_Meerk.png" width="88" alt="Prof. Meerk — la mascotte di Paperfessor" valign="middle"/>
  &nbsp;Paperfessor
</h1>

**Entra una direzione di ricerca. Escono una rassegna della letteratura, esperimenti reali e un articolo formattato per la conferenza.**

[![License: MIT](https://img.shields.io/badge/License-MIT-2E5E4E.svg)](../../LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-33475B.svg)](../../pyproject.toml)

[English](../../README.md) · [简体中文](../zh-CN/README.md) · [日本語](../ja/README.md) · [Español](../es/README.md) · [Français](../fr/README.md) · [Deutsch](../de/README.md) · **Italiano** · [Português](../pt/README.md) · [Русский](../ru/README.md) · [한국어](../ko/README.md) · [العربية](../ar/README.md)

<img src="../../assets/Meerk_studio.png" alt="Lo studio del Prof. Meerk: l'agente dottorando elabora idee e articolo, l'agente magistrale esamina la letteratura, l'agente programmatore esegue gli esperimenti" width="92%"/>

*Dentro lo studio del Prof. Meerk — menti curiose + conoscenza condivisa + iterazione instancabile = impatto reale.*

</div>

---

Paperfessor è un assistente di ricerca a tre agenti che gira sulla tua
macchina con la tua chiave API. Dagli una direzione di ricerca (basta una
frase) e il gruppo di agenti lavora come un piccolo laboratorio:

| Agente | Ruolo | API di stato |
|---|---|---|
| 🎓 **Dottorando** | Inventa il metodo, assegna i compiti, supervisiona, scrive e ispeziona l'articolo | `planning / dispatching / monitoring / reviewing / writing / archiving` |
| 📚 **Studente magistrale** | Ricerca bibliografica ampia (arXiv + OpenAlex + Scholar), lettura integrale rigorosa, estrazione delle evidenze | `websearch / reading / analyzing / reporting / idle / stopped` |
| 💻 **Studente triennale** | Implementa il metodo secondo un contratto rigido, scarica e prepara dati reali, esegue esperimenti a k semi | `coding / thinking / reporting / idle / stopped` |

Ogni numero nell'articolo è **misurato, mai inventato**: i dataset sono veri
download pubblici (i loader rifiutano dati sintetici), il metodo proposto è
verificato eseguendolo davvero e ogni pagina del PDF supera un'ispezione
automatica dell'impaginazione prima che l'esecuzione venga accettata.

## Installazione

```bash
# Python 3.11+
pip install -e ".[gui]"        # da un clone
# oppure, una volta pubblicato:
pip install paperfessor[gui]
```

Per il PDF è consigliato LaTeX (TeX Live/MiKTeX con `acmart`); in mancanza,
ripiego su `.docx` (pandoc) o Markdown.

## Prima configurazione

Le chiavi API vivono nel **portachiavi del sistema operativo** — mai su
disco, mai nei log, mai nell'articolo.

```bash
paperfessor key set minimax --key "sk-..."   # anche openai / anthropic / google
paperfessor key test minimax                 # test di andata e ritorno
paperfessor models list                      # modelli disponibili
```

## Generare un articolo

```bash
paperfessor run "anomaly detection in multivariate time series"
```

Risultati in `workspace/`: `paper/body/paper.pdf` (PDF in formato
conferenza), `src/results/results.json` (metriche misurate, k = 3 semi,
media ± IC 95%), figure reali e i registri di lavoro degli agenti.
Preferisci una finestra? `paperfessor-gui`.

## Uso responsabile e clausola di esonero

Paperfessor è costruito **solo per scopi di ricerca**.

- **Non** presentare il suo output come lavoro proprio non assistito a
  conferenze, riviste o corsi; rispetta le politiche della sede di
  destinazione su assistenza IA, paternità e plagio e dichiara l'assistenza
  dell'IA dove richiesto.
- **Verifica tutto.** Testi, citazioni, codice e numeri generati devono
  essere controllati da una persona prima di qualsiasi uso reale.
- **Non** usarlo per ricerca fabbricata, manipolazione delle citazioni,
  paper mill o qualsiasi scopo illegale o ingannevole.

**Gli autori e i contributori di questo repository non si assumono alcuna
responsabilità per l'uso improprio di questo software né per le conseguenze
derivanti dal suo utilizzo.**

## Licenza

[MIT](../../LICENSE). La mascotte Prof. Meerk fa parte dell'identità del
repository.
