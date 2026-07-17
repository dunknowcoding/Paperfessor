<div align="center">

<h1>
  <img src="../../assets/Prof_Meerk.png" width="88" alt="Prof. Meerk — das Paperfessor-Maskottchen" valign="middle"/>
  &nbsp;Paperfessor
</h1>

**Eine Forschungsrichtung rein. Literaturüberblick, echte Experimente und ein konferenzfertig formatiertes Paper raus.**

[![License: MIT](https://img.shields.io/badge/License-MIT-2E5E4E.svg)](../../LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-33475B.svg)](../../pyproject.toml)

[English](../../README.md) · [简体中文](../zh-CN/README.md) · [日本語](../ja/README.md) · [Español](../es/README.md) · [Français](../fr/README.md) · **Deutsch** · [Italiano](../it/README.md) · [Português](../pt/README.md) · [Русский](../ru/README.md) · [한국어](../ko/README.md) · [العربية](../ar/README.md)

<img src="../../assets/Meerk_studio.png" alt="Prof. Meerks Studio: der Doktoranden-Agent entwirft Ideen und Paper, der Master-Agent sichtet die Literatur, der Coder-Agent fährt die Experimente" width="92%"/>

*In Prof. Meerks Studio — neugierige Köpfe + geteiltes Wissen + unermüdliche Iteration = echte Wirkung.*

</div>

---

Paperfessor ist ein Forschungsassistent mit drei Agenten, der auf deinem
eigenen Rechner mit deinem eigenen API-Schlüssel läuft. Gib ihm eine
Forschungsrichtung (ein Satz genügt), und die Agenten arbeiten wie ein
kleines Labor:

| Agent | Rolle | Status-API |
|---|---|---|
| 🎓 **Doktorand** | Erfindet die Methode, verteilt Aufgaben, überwacht, schreibt und prüft das Paper | `planning / dispatching / monitoring / reviewing / writing / archiving` |
| 📚 **Masterstudent** | Breite Literaturrecherche (arXiv + OpenAlex + Scholar), gründliche Volltextlektüre, Evidenz-Extraktion | `websearch / reading / analyzing / reporting / idle / stopped` |
| 💻 **Bachelorstudent** | Implementiert die Methode nach striktem Vertrag, lädt und verarbeitet echte Daten, fährt k-Seed-Experimente | `coding / thinking / reporting / idle / stopped` |

Jede Zahl im Paper ist **gemessen, niemals erfunden**: Datensätze sind echte
öffentliche Downloads (die Loader verweigern synthetische Platzhalter), die
vorgeschlagene Methode wird durch echtes Ausführen verifiziert, und jede
PDF-Seite besteht eine automatische Layout-Prüfung, bevor ein Lauf
akzeptiert wird.

## Installation

```bash
# Python 3.11+
pip install -e ".[gui]"        # aus einem Klon
# oder nach Veröffentlichung:
pip install paperfessor[gui]
```

Für PDF-Ausgabe wird LaTeX (TeX Live/MiKTeX mit `acmart`) empfohlen; sonst
Rückfall auf `.docx` (pandoc) oder Markdown.

## Ersteinrichtung

API-Schlüssel liegen im **Schlüsselbund des Betriebssystems** — nie auf der
Platte, nie in Logs, nie im Paper.

```bash
paperfessor key set minimax --key "sk-..."   # auch openai / anthropic / google
paperfessor key test minimax                 # Roundtrip-Test
paperfessor models list                      # verfügbare Modelle
```

## Ein Paper erzeugen

```bash
paperfessor run "anomaly detection in multivariate time series"
```

Ergebnisse in `workspace/`: `paper/body/paper.pdf` (konferenzformatiertes
PDF), `src/results/results.json` (gemessene Metriken, k = 3 Seeds,
Mittel ± 95-%-KI), echte Abbildungen und die Arbeitsprotokolle der Agenten.
Lieber ein Fenster? `paperfessor-gui`.

## Verantwortungsvolle Nutzung und Haftungsausschluss

Paperfessor ist **ausschließlich für Forschungszwecke** gebaut.

- **Reiche** seine Ausgabe **nicht** als eigene, unassistierte Arbeit bei
  Konferenzen, Zeitschriften oder Kursen ein; beachte die Richtlinien des
  Zielorts zu KI-Unterstützung, Autorschaft und Plagiat und lege
  KI-Unterstützung offen, wo verlangt.
- **Prüfe alles.** Generierte Texte, Zitate, Code und Zahlen müssen vor
  jeder realen Verwendung von einem Menschen kontrolliert werden.
- **Keine** Nutzung für fabrizierte Forschung, Zitatmanipulation,
  Paper-Mills oder irgendeinen illegalen oder täuschenden Zweck.

**Die Autoren und Mitwirkenden dieses Repositories übernehmen keinerlei
Verantwortung oder Haftung für Missbrauch dieser Software oder für Folgen
ihrer Nutzung.**

## Lizenz

[MIT](../../LICENSE). Das Prof.-Meerk-Maskottchen ist Teil des Brandings
dieses Repositories.
