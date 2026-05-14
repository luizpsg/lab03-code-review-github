# LAB03 — Caracterizando a atividade de code review no GitHub

Trabalho desenvolvido na disciplina **Laboratório de Experimentação de Software** (PUC Minas), prof. **Danilo de Quadros Maia Filho**.

Autores: Luiz Paulo Gonçalves, Arthur Curi, Hélio Ernesto.

O projeto coleta dados de Pull Requests dos 200 repositórios mais populares do GitHub, calcula métricas relacionadas a code review e responde a 8 questões de pesquisa usando o teste de correlação de Spearman.

## Pré-requisitos

- Python 3.11+ (testado com 3.12).
- Conta GitHub e um **Personal Access Token** com escopo `public_repo` (https://github.com/settings/tokens).
- Para compilar o relatório em PDF: `latexmk` + `pdflatex` (TeX Live, MiKTeX) **ou** Overleaf.

## Setup

```bash
# 1. Criar virtualenv (opcional, recomendado)
python -m venv .venv
.venv\Scripts\activate            # Windows PowerShell
# source .venv/bin/activate      # Linux/macOS

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar o token
copy .env.example .env             # Windows
# cp .env.example .env            # Linux/macOS
# edite o .env e coloque seu GITHUB_TOKEN
```

## Execução

Pipeline completo (recomendado):

```bash
python main.py
```

O `main.py` orquestra na ordem:

1. `src/collect_repos.py` — coleta os top 200 repositorios por estrelas via GraphQL e mantém apenas os que possuem `pullRequests(MERGED+CLOSED).totalCount >= 100`. Salva `data/repos.csv`.
2. `src/collect_prs.py` — para cada repositorio coleta até `PR_LIMIT_PER_REPO=200` PRs (mais recentes), com **checkpoint idempotente por repo** em `data/checkpoints/`. Trata rate-limit (espera até `resetAt` quando `remaining < 50`) e faz retry exponencial. Salva `data/prs_raw.csv`.
3. `src/build_dataset.py` — aplica os filtros do enunciado (status `MERGED`/`CLOSED`, `reviews >= 1`, tempo de análise `> 1h`) e produz `data/dataset_final.csv`.
4. `src/analysis.py` — calcula medianas, correlações de Spearman para as 8 RQs, gera as figuras em `figures/` e o `data/results_summary.json`.
5. `src/report_builder.py` — preenche `report/relatorio.tex` com os valores reais.

Cada script também pode ser executado isoladamente. Tudo é idempotente: se você interromper a coleta, basta rodar de novo e ele retoma do checkpoint.

## Saídas

- `data/repos.csv` — lista filtrada de repositorios.
- `data/prs_raw.csv` — todos os PRs coletados (antes dos filtros do dataset final).
- `data/dataset_final.csv` — dataset usado nas análises.
- `data/results_summary.json` — todas as medianas, rho e p-valores.
- `figures/*.png` — boxplots, scatter plots e heatmap (300 dpi, PT-BR).
- `report/relatorio.tex` — relatório final em LaTeX, formato artigo, PT-BR.

## Compilação do relatório

Com LaTeX instalado:

```bash
cd report
latexmk -pdf relatorio.tex
```

Sem LaTeX local: faça upload do `relatorio.tex` e da pasta `figures/` para o [Overleaf](https://www.overleaf.com).

## Estrutura do projeto

```
.
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── main.py
├── src/
│   ├── __init__.py
│   ├── github_client.py
│   ├── collect_repos.py
│   ├── collect_prs.py
│   ├── build_dataset.py
│   ├── analysis.py
│   └── report_builder.py
├── data/
│   ├── repos.csv
│   ├── prs_raw.csv
│   ├── dataset_final.csv
│   ├── results_summary.json
│   └── checkpoints/
├── figures/
└── report/
    └── relatorio.tex
```

## Métricas coletadas por PR

| Dimensão | Métrica | Campo GraphQL |
|---|---|---|
| Tamanho | arquivos alterados | `changedFiles` |
| Tamanho | linhas alteradas (add+del) | `additions + deletions` |
| Tempo | tempo de análise (h) | `mergedAt`/`closedAt` − `createdAt` |
| Descrição | tamanho do corpo (chars) | `bodyText` |
| Interação | participantes | `participants.totalCount` |
| Interação | comentários | `comments.totalCount` |
| Resultado | status | `state` (MERGED/CLOSED) |
| Resultado | revisões | `reviews.totalCount` |

## Questões de pesquisa

**Dimensão A — Feedback final (MERGED vs CLOSED)**

- RQ01: relação entre tamanho dos PRs e feedback final.
- RQ02: relação entre tempo de análise e feedback final.
- RQ03: relação entre descrição e feedback final.
- RQ04: relação entre interações e feedback final.

**Dimensão B — Número de revisões**

- RQ05: relação entre tamanho dos PRs e número de revisões.
- RQ06: relação entre tempo de análise e número de revisões.
- RQ07: relação entre descrição e número de revisões.
- RQ08: relação entre interações e número de revisões.

Para todas as RQs usamos o teste de **correlação de Spearman** (ver justificativa na seção de Metodologia do relatório).
