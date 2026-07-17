<div align="center">

<h1>
  <img src="../../assets/Prof_Meerk.png" width="88" alt="Prof. Meerk — la mascotte de Paperfessor" valign="middle"/>
  &nbsp;Paperfessor
</h1>

**Une direction de recherche en entrée. Une revue de littérature, de vraies expériences et un article au format conférence en sortie.**

[![License: MIT](https://img.shields.io/badge/License-MIT-2E5E4E.svg)](../../LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-33475B.svg)](../../pyproject.toml)

[English](../../README.md) · [简体中文](../zh-CN/README.md) · [日本語](../ja/README.md) · [Español](../es/README.md) · **Français** · [Deutsch](../de/README.md) · [Italiano](../it/README.md) · [Português](../pt/README.md) · [Русский](../ru/README.md) · [한국어](../ko/README.md) · [العربية](../ar/README.md)

<img src="../../assets/Meerk_studio.png" alt="Le studio du Prof. Meerk : l'agent doctorant conçoit les idées et l'article, l'agent master analyse la littérature, l'agent codeur mène les expériences" width="92%"/>

*Dans le studio du Prof. Meerk — esprits curieux + savoir partagé + itération sans relâche = impact réel.*

</div>

---

Paperfessor est un assistant de recherche à trois agents qui tourne sur votre
machine avec votre propre clé d'API. Donnez-lui une direction de recherche
(une phrase suffit) et son groupe d'agents travaille comme un petit
laboratoire :

| Agent | Rôle | API d'état |
|---|---|---|
| 🎓 **Doctorant** | Invente la méthode, distribue les tâches, supervise, rédige et inspecte l'article | `planning / dispatching / monitoring / reviewing / writing / archiving` |
| 📚 **Étudiant en master** | Recherche bibliographique large (arXiv + OpenAlex + Scholar), lecture intégrale rigoureuse, extraction de preuves | `websearch / reading / analyzing / reporting / idle / stopped` |
| 💻 **Étudiant de licence** | Implémente la méthode sous contrat strict, télécharge et prépare de vraies données, lance les expériences à k graines | `coding / thinking / reporting / idle / stopped` |

Chaque nombre de l'article est **mesuré, jamais inventé** : les jeux de
données sont de vrais téléchargements publics (les chargeurs refusent les
données synthétiques), la méthode proposée est vérifiée par exécution réelle,
et chaque page du PDF passe une inspection automatique de mise en page avant
que l'exécution soit acceptée.

## Installation

```bash
# Python 3.11+
pip install -e ".[gui]"        # depuis un clone
# ou, une fois publié :
pip install paperfessor[gui]
```

LaTeX (TeX Live/MiKTeX avec `acmart`) est recommandé pour le PDF ; sinon,
repli sur `.docx` (pandoc) ou Markdown.

## Première configuration

Les clés d'API vivent dans le **trousseau du système** — jamais sur disque,
ni dans les journaux, ni dans l'article.

```bash
paperfessor key set minimax --key "sk-..."   # aussi openai / anthropic / google
paperfessor key test minimax                 # test aller-retour
paperfessor models list                      # modèles disponibles
```

## Produire un article

```bash
paperfessor run "anomaly detection in multivariate time series"
```

Résultats dans `workspace/` : `paper/body/paper.pdf` (PDF au format
conférence), `src/results/results.json` (métriques mesurées, k = 3 graines,
moyenne ± IC 95 %), figures réelles et journaux de travail des agents.
Une fenêtre ? `paperfessor-gui`.

## Usage responsable et avertissement

Paperfessor est conçu **à des fins de recherche uniquement**.

- **Ne soumettez pas** sa sortie comme votre travail personnel non assisté à
  des conférences, revues ou cours ; respectez les politiques du lieu visé
  sur l'assistance par IA, la paternité et le plagiat, et déclarez
  l'assistance de l'IA lorsque c'est requis.
- **Vérifiez tout.** Textes, citations, code et nombres générés doivent être
  contrôlés par un humain avant tout usage réel.
- **N'utilisez pas** l'outil pour de la recherche fabriquée, la manipulation
  de citations, les usines à articles ou tout usage illégal ou trompeur.

**Les auteurs et contributeurs de ce dépôt déclinent toute responsabilité
quant au mésusage de ce logiciel et à toute conséquence de son utilisation.**

## Licence

[MIT](../../LICENSE). La mascotte Prof. Meerk fait partie de l'identité du
dépôt.
