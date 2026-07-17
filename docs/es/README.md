<div align="center">

<h1>
  <img src="../../assets/Prof_Meerk.png" width="88" alt="Prof. Meerk — la mascota de Paperfessor" valign="middle"/>
  &nbsp;Paperfessor
</h1>

**Entra una dirección de investigación. Salen una revisión bibliográfica, experimentos reales y un artículo con formato de congreso.**

[![License: MIT](https://img.shields.io/badge/License-MIT-2E5E4E.svg)](../../LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-33475B.svg)](../../pyproject.toml)

[English](../../README.md) · [简体中文](../zh-CN/README.md) · [日本語](../ja/README.md) · **Español** · [Français](../fr/README.md) · [Deutsch](../de/README.md) · [Italiano](../it/README.md) · [Português](../pt/README.md) · [Русский](../ru/README.md) · [한국어](../ko/README.md) · [العربية](../ar/README.md)

<img src="../../assets/Meerk_studio.png" alt="El estudio del Prof. Meerk: el agente doctorando redacta ideas y el artículo, el agente de máster revisa la literatura y el agente programador ejecuta los experimentos" width="92%"/>

*Dentro del estudio del Prof. Meerk — mentes curiosas + conocimiento compartido + iteración incansable = impacto real.*

</div>

---

Paperfessor es un asistente de investigación con tres agentes que se ejecuta en
tu propia máquina y con tu propia clave de API. Dale una dirección de
investigación (una frase basta) y su grupo de agentes trabaja como un pequeño
laboratorio:

| Agente | Rol | API de estado |
|---|---|---|
| 🎓 **Doctorando** | Inventa el método, asigna tareas, supervisa, escribe e inspecciona el artículo | `planning / dispatching / monitoring / reviewing / writing / archiving` |
| 📚 **Estudiante de máster** | Búsqueda bibliográfica amplia (arXiv + OpenAlex + Scholar), lectura rigurosa del texto completo, extracción de evidencia | `websearch / reading / analyzing / reporting / idle / stopped` |
| 💻 **Estudiante de grado** | Implementa el método bajo un contrato estricto, descarga y preprocesa datos reales, ejecuta experimentos con k semillas | `coding / thinking / reporting / idle / stopped` |

Cada número del artículo está **medido, nunca inventado**: los datos son
descargas públicas reales (los cargadores rechazan datos sintéticos), el método
propuesto se verifica ejecutándolo de verdad y cada página del PDF pasa una
inspección automática de maquetación antes de aceptar la ejecución.

## Instalación

```bash
# Python 3.11+
pip install -e ".[gui]"        # desde un clon
# o, una vez publicado:
pip install paperfessor[gui]
```

Se recomienda LaTeX (TeX Live/MiKTeX con `acmart`) para el PDF; sin él,
Paperfessor recurre a `.docx` (pandoc) o Markdown.

## Primera configuración

Las claves de API viven en el **llavero del sistema operativo** — nunca en
disco, ni en registros, ni en el artículo.

```bash
paperfessor key set minimax --key "sk-..."   # también openai / anthropic / google
paperfessor key test minimax                 # prueba de ida y vuelta
paperfessor models list                      # modelos disponibles
```

## Generar un artículo

```bash
paperfessor run "anomaly detection in multivariate time series"
```

Resultados en `workspace/`: `paper/body/paper.pdf` (PDF con formato de
congreso), `src/results/results.json` (métricas medidas, k = 3 semillas,
media ± IC del 95 %), figuras reales y los registros de trabajo de los agentes.
¿Prefieres una ventana? `paperfessor-gui`.

## Uso responsable y descargo de responsabilidad

Paperfessor está construido **solo con fines de investigación**.

- **No** presentes su salida como trabajo propio sin asistencia en congresos,
  revistas o cursos; cumple las políticas del lugar de destino sobre
  asistencia de IA, autoría y plagio, y declara la asistencia de IA cuando
  se requiera.
- **Verifica todo.** Texto, citas, código y números generados deben ser
  revisados por una persona antes de cualquier uso real.
- **No** lo uses para investigación fabricada, manipulación de citas,
  fábricas de artículos ni ningún fin ilegal o engañoso.

**Los autores y colaboradores de este repositorio no aceptan ninguna
responsabilidad por el mal uso de este software ni por las consecuencias
derivadas de su uso.**

## Licencia

[MIT](../../LICENSE). La mascota Prof. Meerk forma parte de la identidad de
este repositorio.
