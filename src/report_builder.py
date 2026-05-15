"""Gera o relatorio LaTeX final (report/relatorio.tex) com valores reais."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("lab03.report")

# Hipoteses informais por RQ (do enunciado: "o que eu espero encontrar e por que").
HYPOTHESES = {
    "RQ01": {
        "direction": "negativa",
        "text": (
            "PRs maiores tendem a introduzir mais riscos e demandam revisao mais detalhada, "
            "logo esperamos que PRs com maior numero de arquivos alterados (e mais linhas modificadas) "
            "tenham menor probabilidade de serem aceitos."
        ),
    },
    "RQ02": {
        "direction": "negativa",
        "text": (
            "Esperamos correlacao negativa: PRs que permanecem muito tempo em revisao costumam "
            "indicar discussoes prolongadas ou problemas que tendem a culminar em fechamento sem merge."
        ),
    },
    "RQ03": {
        "direction": "positiva",
        "text": (
            "Esperamos correlacao positiva: descricoes mais detalhadas fornecem contexto aos revisores "
            "e facilitam a aceitacao do PR."
        ),
    },
    "RQ04": {
        "direction": "mista",
        "text": (
            "Esperamos efeito misto: por um lado mais participantes e comentarios indicam atencao "
            "ao PR; por outro, podem refletir controversia e questionamentos, podendo correlacionar-se "
            "negativamente com o merge."
        ),
    },
    "RQ05": {
        "direction": "positiva",
        "text": (
            "Esperamos correlacao positiva: PRs maiores tendem a passar por mais rodadas de revisao."
        ),
    },
    "RQ06": {
        "direction": "positiva",
        "text": (
            "Esperamos correlacao positiva: quanto mais tempo em revisao, maior a oportunidade de "
            "novas revisoes ocorrerem."
        ),
    },
    "RQ07": {
        "direction": "negativa",
        "text": (
            "Esperamos correlacao negativa (ou pequena): descricoes ricas reduziriam duvidas e, "
            "portanto, a necessidade de rodadas adicionais de revisao."
        ),
    },
    "RQ08": {
        "direction": "positiva",
        "text": (
            "Esperamos correlacao positiva: PRs com mais participantes e comentarios devem demandar "
            "mais revisoes."
        ),
    },
}

METRIC_PT = {
    "changed_files": "arquivos alterados",
    "lines_changed": "linhas alteradas (additions + deletions)",
    "analysis_time_hours": "tempo de analise (horas)",
    "body_length_chars": "tamanho da descricao (caracteres)",
    "participants_count": "numero de participantes",
    "comments_count": "numero de comentarios",
    "reviews_count": "numero de revisoes",
}


def _fmt(value: float, digits: int = 4) -> str:
    if value is None or value != value:
        return "--"
    return f"{value:.{digits}f}".replace(".", ",")


def _fmt_p_inline(value: float) -> str:
    """Formata p-valor em conteudo matematico para uso inline em ($p\\,{pv}$).

    Retorna "= 0{,}1234" ou "< 0{,}0001".
    """
    if value is None or value != value:
        return "= --"
    if value < 1e-4:
        return "< 0{,}0001"
    return "= " + _fmt(value, 4).replace(",", "{,}")


def _fmt_p_table(value: float) -> str:
    """Formata p-valor para celula de tabela (conteudo matematico, sem prefixo)."""
    if value is None or value != value:
        return "--"
    if value < 1e-4:
        return "< 0{,}0001"
    return _fmt(value, 4).replace(",", "{,}")


def _fmt_int(value: float) -> str:
    return f"{int(round(value)):,}".replace(",", ".")


def _strength(rho: float) -> str:
    if rho is None or rho != rho:
        return "indeterminada"
    a = abs(rho)
    if a < 0.1:
        return "muito fraca"
    if a < 0.3:
        return "fraca"
    if a < 0.5:
        return "moderada"
    if a < 0.7:
        return "forte"
    return "muito forte"


def _direction(rho: float) -> str:
    if rho is None or rho != rho:
        return "indefinida"
    if rho > 0:
        return "positiva"
    if rho < 0:
        return "negativa"
    return "nula"


def _matches_hypothesis(rq: str, rho: float) -> str:
    expected = HYPOTHESES[rq]["direction"]
    actual = _direction(rho)
    if expected == "mista":
        return "compativel (hipotese era mista)"
    if abs(rho) < 0.05:
        return "nao se confirma (correlacao desprezivel)"
    if expected == actual:
        return "confirmada"
    return "refutada"


def _ascii(text: str) -> str:
    replacements = {
        "á": r"\'a", "à": r"\`a", "â": r"\^a", "ã": r"\~a", "ä": r'\"a',
        "é": r"\'e", "ê": r"\^e", "ë": r'\"e',
        "í": r"\'i", "ï": r'\"i',
        "ó": r"\'o", "ô": r"\^o", "õ": r"\~o", "ö": r'\"o',
        "ú": r"\'u", "ü": r'\"u',
        "ç": r"\c{c}",
        "Á": r"\'A", "É": r"\'E", "Í": r"\'I", "Ó": r"\'O", "Ú": r"\'U",
        "Â": r"\^A", "Ê": r"\^E", "Ô": r"\^O",
        "Ã": r"\~A", "Õ": r"\~O",
        "Ç": r"\c{C}",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text


def _rq_result(summary: dict, rq: str, metric: str | None = None) -> dict | None:
    for r in summary["rq_results"]:
        if r["rq"] == rq and (metric is None or r["metric"] == metric):
            return r
    return None


def _table_medians(summary: dict) -> str:
    lines = [
        r"\begin{table}[H]",
        r"\centering",
        r"\caption{Medianas das m\'etricas globais e por status do PR.}",
        r"\label{tab:medianas}",
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r"M\'etrica & Geral & MERGED & CLOSED \\",
        r"\midrule",
    ]
    metrics_order = [
        "changed_files",
        "lines_changed",
        "analysis_time_hours",
        "body_length_chars",
        "participants_count",
        "comments_count",
        "reviews_count",
    ]
    for m in metrics_order:
        label = _ascii(METRIC_PT[m].capitalize())
        ov = summary["medians_overall"][m]
        me = summary["medians_by_status"]["MERGED"][m]
        cl = summary["medians_by_status"]["CLOSED"][m]
        lines.append(
            f"{label} & {_fmt(ov, 2)} & {_fmt(me, 2)} & {_fmt(cl, 2)} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


def _table_rqs(summary: dict) -> str:
    lines = [
        r"\begin{table}[H]",
        r"\centering",
        r"\caption{Resumo das 8 RQs: correla\c{c}\~ao de Spearman entre cada m\'etrica e a vari\'avel dependente.}",
        r"\label{tab:rqs}",
        r"\begin{tabular}{llrrr}",
        r"\toprule",
        r"RQ & M\'etrica & $\rho$ & $p$-valor & $n$ \\",
        r"\midrule",
    ]
    for r in summary["rq_results"]:
        label = _ascii(METRIC_PT[r["metric"]])
        rho_str = _fmt(r["spearman_rho"], 4).replace(",", "{,}")
        p_str = _fmt_p_table(r["p_value"])
        lines.append(
            f"{r['rq']} & {label} & ${rho_str}$ & ${p_str}$ & {_fmt_int(r['n'])} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


def _rq_paragraph_status(summary: dict, rq: str) -> str:
    results = [r for r in summary["rq_results"] if r["rq"] == rq]
    if not results:
        return ""
    parts = []
    for r in results:
        med_m = _fmt(r["median_merged"], 2)
        med_c = _fmt(r["median_closed"], 2)
        rho = _fmt(r["spearman_rho"], 4).replace(",", "{,}")
        pv = _fmt_p_inline(r["p_value"])
        metric_label = _ascii(METRIC_PT[r["metric"]])
        parts.append(
            f"Para {metric_label}, a mediana entre PRs aceitos (MERGED) foi {med_m} "
            f"e entre rejeitados (CLOSED) foi {med_c}. A correla\\c{{c}}\\~ao de Spearman "
            f"com o status (MERGED=1, CLOSED=0) resultou em $\\rho = {rho}$ "
            f"($p\\,{pv}$). Veja a Figura~\\ref{{fig:{r['figure'].split('.')[0]}}}."
        )
    return " ".join(parts)


def _rq_paragraph_reviews(summary: dict, rq: str) -> str:
    results = [r for r in summary["rq_results"] if r["rq"] == rq]
    if not results:
        return ""
    parts = []
    for r in results:
        rho = _fmt(r["spearman_rho"], 4).replace(",", "{,}")
        pv = _fmt_p_inline(r["p_value"])
        metric_label = _ascii(METRIC_PT[r["metric"]])
        parts.append(
            f"Para {metric_label}, a correla\\c{{c}}\\~ao de Spearman com o n\\'umero de "
            f"revis\\~oes resultou em $\\rho = {rho}$ ($p\\,{pv}$). "
            f"Veja a Figura~\\ref{{fig:{r['figure'].split('.')[0]}}}."
        )
    return " ".join(parts)


def _figures_block(summary: dict, rq: str) -> str:
    results = [r for r in summary["rq_results"] if r["rq"] == rq]
    blocks = []
    for r in results:
        fig_name = r["figure"]
        label = fig_name.split(".")[0]
        caption = _ascii(f"{rq} - {METRIC_PT[r['metric']]}")
        blocks.append(
            "\n".join(
                [
                    r"\begin{figure}[H]",
                    r"\centering",
                    rf"\includegraphics[width=0.78\textwidth]{{../figures/{fig_name}}}",
                    rf"\caption{{{caption}}}",
                    rf"\label{{fig:{label}}}",
                    r"\end{figure}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _discussion(summary: dict, rq: str) -> str:
    results = [r for r in summary["rq_results"] if r["rq"] == rq]
    hyp = HYPOTHESES[rq]
    parts = [_ascii(f"Hipotese inicial: {hyp['text']}")]
    for r in results:
        rho = r["spearman_rho"]
        verdict = _matches_hypothesis(rq, rho)
        parts.append(
            _ascii(
                f"Para {METRIC_PT[r['metric']]}, obtivemos rho = {_fmt(rho, 4)} "
                f"(intensidade {_strength(rho)}, direcao {_direction(rho)}); "
                f"hipotese {verdict}."
            )
        )
    return " ".join(parts)


def build_report(summary_path: Path, output_path: Path) -> Path:
    with summary_path.open(encoding="utf-8") as f:
        summary = json.load(f)

    n_total = _fmt_int(summary["n_total"])
    n_merged = _fmt_int(summary["n_merged"])
    n_closed = _fmt_int(summary["n_closed"])
    n_repos = _fmt_int(summary["n_repos"])

    table_medians = _table_medians(summary)
    table_rqs = _table_rqs(summary)

    rqs_status = ["RQ01", "RQ02", "RQ03", "RQ04"]
    rqs_reviews = ["RQ05", "RQ06", "RQ07", "RQ08"]

    results_sections = []
    for rq in rqs_status:
        results_sections.append(
            f"\\subsection*{{{rq}}}\n"
            f"{_rq_paragraph_status(summary, rq)}\n\n"
            f"{_figures_block(summary, rq)}"
        )
    for rq in rqs_reviews:
        results_sections.append(
            f"\\subsection*{{{rq}}}\n"
            f"{_rq_paragraph_reviews(summary, rq)}\n\n"
            f"{_figures_block(summary, rq)}"
        )

    discussion_sections = []
    for rq in rqs_status + rqs_reviews:
        discussion_sections.append(
            f"\\subsection*{{{rq}}}\n{_discussion(summary, rq)}"
        )

    heatmap_block = "\n".join(
        [
            r"\begin{figure}[H]",
            r"\centering",
            r"\includegraphics[width=0.85\textwidth]{../figures/heatmap_correlacoes.png}",
            r"\caption{Heatmap de correla\c{c}\~oes (Spearman) entre todas as m\'etricas.}",
            r"\label{fig:heatmap}",
            r"\end{figure}",
        ]
    )

    intro_hyps = []
    for rq in rqs_status + rqs_reviews:
        intro_hyps.append(
            _ascii(f"\\textbf{{{rq}}}: {HYPOTHESES[rq]['text']}")
        )
    intro_hyps_block = "\\\\\n".join(intro_hyps)

    tex = rf"""\documentclass[11pt,a4paper]{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage[brazil]{{babel}}
\usepackage[a4paper,margin=2.5cm]{{geometry}}
\usepackage{{graphicx}}
\usepackage{{booktabs}}
\usepackage{{float}}
\usepackage{{caption}}
\usepackage{{hyperref}}
\hypersetup{{colorlinks=true,linkcolor=blue,citecolor=blue,urlcolor=blue}}

\title{{Caracterizando a atividade de \emph{{code review}} no GitHub}}
\author{{Luiz Paulo Gon\c{{c}}alves \and Arthur Curi \and H\'elio Ernesto \\
PUC Minas -- Laborat\'orio de Experimenta\c{{c}}\~ao de Software \\
Prof. Danilo de Quadros Maia Filho}}
\date{{\today}}

\begin{{document}}
\maketitle

\begin{{abstract}}
Este trabalho caracteriza a atividade de \emph{{code review}} em reposit\'orios populares do GitHub,
sob a perspectiva de quem submete c\'odigo. Coletamos {n_total} \emph{{Pull Requests}} a partir de
{n_repos} reposit\'orios entre os 200 mais populares por estrelas, contemplando apenas PRs com
status MERGED ou CLOSED, pelo menos uma revis\~ao registrada e tempo de an\'alise superior a uma hora.
Analisamos oito quest\~oes de pesquisa em duas dimens\~oes: o \emph{{feedback}} final da revis\~ao
(MERGED vs.\ CLOSED) e o n\'umero de revis\~oes realizadas, considerando como vari\'aveis
independentes o tamanho do PR, o tempo de an\'alise, a riqueza da descri\c{{c}}\~ao e o volume de
intera\c{{c}}\~oes. Utilizamos o teste de correla\c{{c}}\~ao de Spearman, adequado a dados
n\~ao-normais e \`a presen\c{{c}}a de \emph{{outliers}}, e reportamos coeficiente $\rho$ e
$p$-valor para cada RQ.
\end{{abstract}}

\section{{Introdu\c{{c}}\~ao}}

Revis\~ao de c\'odigo (\emph{{code review}}) tornou-se pr\'atica central no desenvolvimento
moderno, especialmente em projetos \emph{{open source}} hospedados no GitHub. Por meio de
\emph{{Pull Requests}}, contribuidores submetem mudan\c{{c}}as que s\~ao discutidas, comentadas e
eventualmente aceitas (\emph{{merged}}) ou rejeitadas (\emph{{closed}}). Compreender quais
caracter\'isticas dos PRs influenciam a aceita\c{{c}}\~ao e a quantidade de revis\~oes recebidas
\'e fundamental para que submissores escrevam contribui\c{{c}}\~oes mais efetivas.

Neste trabalho buscamos responder a oito quest\~oes de pesquisa organizadas em duas dimens\~oes:
(A) o \emph{{feedback}} final da revis\~ao --- representado pelo status MERGED ou CLOSED --- e
(B) o n\'umero de revis\~oes (\emph{{reviews}}) registradas no PR. Em cada dimens\~ao consideramos
quatro vari\'aveis independentes: tamanho, tempo de an\'alise, descri\c{{c}}\~ao e intera\c{{c}}\~oes.

\paragraph{{Hip\'oteses informais.}}
Antes de coletar os dados, formulamos as seguintes expectativas para cada RQ:

\medskip
{intro_hyps_block}

\section{{Metodologia}}

\subsection*{{Constru\c{{c}}\~ao do \emph{{dataset}}}}

Os dados foram obtidos via API GraphQL do GitHub (\url{{https://api.github.com/graphql}}).
Inicialmente listamos os 200 reposit\'orios p\'ublicos com mais estrelas, mantendo apenas
aqueles com pelo menos 100 \emph{{Pull Requests}} no estado MERGED ou CLOSED. Para cada
reposit\'orio coletamos os \emph{{Pull Requests}} mais recentes at\'e o limite configur\'avel
\texttt{{PR\_LIMIT\_PER\_REPO}} (configurado como 200 nesta execu\c{{c}}\~ao), parametro que
explicitamente controla o tempo de execu\c{{c}}\~ao da coleta.

Aplicamos os seguintes filtros sobre cada PR:

\begin{{itemize}}
  \item status \texttt{{MERGED}} ou \texttt{{CLOSED}};
  \item pelo menos uma revis\~ao registrada (\texttt{{reviews.totalCount}} $\geq 1$);
  \item tempo de an\'alise superior a uma hora --- diferen\c{{c}}a entre \texttt{{createdAt}}
        e a \'ultima atividade (\texttt{{mergedAt}} ou \texttt{{closedAt}}). Esse crit\'erio
        elimina PRs revisados de forma autom\'atica por \emph{{bots}} ou CI.
\end{{itemize}}

A coleta \'e robusta: trata \emph{{rate limit}} prim\'ario (pausa at\'e \texttt{{resetAt}}
quando o or\c{{c}}amento de pontos est\'a baixo), \emph{{secondary rate limit}} (\emph{{retry}}
com \emph{{backoff}} exponencial), e mant\'em \emph{{checkpoint}} por reposit\'orio (arquivos
JSON em \texttt{{data/checkpoints/}}), permitindo retomar de onde parou em caso de interrup\c{{c}}\~ao.

Ap\'os o filtro, o \emph{{dataset}} final cont\'em {n_total} PRs distribu\'idos em {n_repos}
reposit\'orios, dos quais {n_merged} foram aceitos (MERGED) e {n_closed} rejeitados (CLOSED).

\subsection*{{M\'etricas por PR}}

\begin{{itemize}}
  \item \textbf{{Tamanho}}: n\'umero de arquivos alterados (\texttt{{changedFiles}}) e total
        de linhas adicionadas mais removidas (\texttt{{additions + deletions}}).
  \item \textbf{{Tempo de an\'alise}}: intervalo em horas entre \texttt{{createdAt}} e
        \texttt{{mergedAt}}/\texttt{{closedAt}}.
  \item \textbf{{Descri\c{{c}}\~ao}}: n\'umero de caracteres do corpo do PR (\texttt{{bodyText}}).
  \item \textbf{{Intera\c{{c}}\~oes}}: \texttt{{participants.totalCount}} e
        \texttt{{comments.totalCount}}.
  \item \textbf{{N\'umero de revis\~oes}}: \texttt{{reviews.totalCount}}.
\end{{itemize}}

\subsection*{{An\'alise estat\'istica}}

Para cada RQ sumarizamos pelos valores \emph{{medianos}} sobre todos os PRs do \emph{{dataset}}
(sem agregar por reposit\'orio). Adotamos o teste de \textbf{{correla\c{{c}}\~ao de Spearman}} pelos
seguintes motivos:
(i) as distribui\c{{c}}\~oes das m\'etricas s\~ao fortemente assim\'etricas e apresentam
\emph{{outliers}} (tamanho e tempo costumam ter cauda longa);
(ii) n\~ao h\'a evid\^encia de normalidade --- requisito do teste de Pearson;
(iii) Spearman captura rela\c{{c}}\~oes monot\^onicas (e n\~ao apenas estritamente lineares),
o que \'e mais aderente \`a natureza dos dados de \emph{{code review}}.

Para as RQs da dimens\~ao A (status como vari\'avel dependente) codificamos o status como
bin\'ario (MERGED=1, CLOSED=0) e calculamos $\rho$ e $p$-valor entre a m\'etrica e o
status; tamb\'em reportamos as medianas das m\'etricas por grupo (MERGED vs.\ CLOSED).
Para as RQs da dimens\~ao B aplicamos Spearman diretamente entre a m\'etrica e
\texttt{{reviews.totalCount}}.

\section{{Resultados}}

A Tabela~\ref{{tab:medianas}} apresenta as medianas das m\'etricas, globais e por status.
A Tabela~\ref{{tab:rqs}} resume as correla\c{{c}}\~oes de Spearman para as oito RQs.

{table_medians}

{table_rqs}

\subsection{{Dimens\~ao A -- \emph{{Feedback}} final (MERGED vs.\ CLOSED)}}

{results_sections[0]}

{results_sections[1]}

{results_sections[2]}

{results_sections[3]}

\subsection{{Dimens\~ao B -- N\'umero de revis\~oes}}

{results_sections[4]}

{results_sections[5]}

{results_sections[6]}

{results_sections[7]}

\subsection{{Vis\~ao geral das correla\c{{c}}\~oes}}

{heatmap_block}

\section{{Discuss\~ao}}

Nesta se\c{{c}}\~ao confrontamos as hip\'oteses iniciais com os valores observados.
Adotamos a seguinte conven\c{{c}}\~ao de intensidade para $|\rho|$: muito fraca ($< 0{{,}}1$),
fraca ($< 0{{,}}3$), moderada ($< 0{{,}}5$), forte ($< 0{{,}}7$) e muito forte ($\geq 0{{,}}7$).

{discussion_sections[0]}

{discussion_sections[1]}

{discussion_sections[2]}

{discussion_sections[3]}

{discussion_sections[4]}

{discussion_sections[5]}

{discussion_sections[6]}

{discussion_sections[7]}

\section{{Conclus\~ao}}

Caracterizamos a atividade de \emph{{code review}} em {n_repos} reposit\'orios populares do GitHub
analisando {n_total} \emph{{Pull Requests}} sob duas dimens\~oes: o \emph{{feedback}} final
(MERGED vs.\ CLOSED) e o n\'umero de revis\~oes. As principais observa\c{{c}}\~oes est\~ao
sumarizadas na Tabela~\ref{{tab:rqs}} e nas Figuras correspondentes a cada RQ.

Como limita\c{{c}}\~oes destacam-se: (i) o teto de {n_repos} reposit\'orios e o limite
\texttt{{PR\_LIMIT\_PER\_REPO}} podem n\~ao representar comunidades de menor visibilidade;
(ii) o filtro de tempo $>$ 1h, embora elimine ru\'idos de \emph{{bots}}, pode descartar PRs
triviais leg\'itimos; (iii) o uso de \emph{{Spearman}} captura monotonicidade, mas n\~ao
implica causalidade. Trabalhos futuros podem incorporar an\'alises multivariadas e estratifica\c{{c}}\~ao
por linguagem ou dom\'inio do reposit\'orio.

\end{{document}}
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(tex, encoding="utf-8")
    logger.info("Relatorio LaTeX gerado em %s", output_path)
    return output_path


def main() -> Path:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    summary_path = Path("data/results_summary.json")
    if not summary_path.exists():
        raise FileNotFoundError(
            "data/results_summary.json nao encontrado. Rode analysis.py antes."
        )
    output_path = Path("report/relatorio.tex")
    return build_report(summary_path, output_path)


if __name__ == "__main__":
    main()
