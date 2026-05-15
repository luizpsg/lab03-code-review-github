"""Analise estatistica das 8 RQs: medianas, Spearman, figuras e summary JSON."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

logger = logging.getLogger("lab03.analysis")

# Eixo: nome interno -> rotulo em PT-BR para os graficos.
METRIC_LABELS = {
    "changed_files": "Arquivos alterados",
    "lines_changed": "Linhas alteradas (add+del)",
    "analysis_time_hours": "Tempo de analise (horas)",
    "body_length_chars": "Tamanho da descricao (caracteres)",
    "participants_count": "Numero de participantes",
    "comments_count": "Numero de comentarios",
    "reviews_count": "Numero de revisoes",
}

# Mapeamento RQ -> metrica usada (dimensao A).
RQ_STATUS_METRICS = {
    "RQ01": ["changed_files", "lines_changed"],
    "RQ02": ["analysis_time_hours"],
    "RQ03": ["body_length_chars"],
    "RQ04": ["participants_count", "comments_count"],
}

# Mapeamento RQ -> metrica usada (dimensao B).
RQ_REVIEWS_METRICS = {
    "RQ05": ["changed_files", "lines_changed"],
    "RQ06": ["analysis_time_hours"],
    "RQ07": ["body_length_chars"],
    "RQ08": ["participants_count", "comments_count"],
}

RQ_DIMENSION_LABELS = {
    "RQ01": "Tamanho",
    "RQ02": "Tempo de analise",
    "RQ03": "Descricao",
    "RQ04": "Interacoes",
    "RQ05": "Tamanho",
    "RQ06": "Tempo de analise",
    "RQ07": "Descricao",
    "RQ08": "Interacoes",
}


def _ensure_dirs(figures_dir: Path) -> None:
    figures_dir.mkdir(parents=True, exist_ok=True)


def _spearman(x: pd.Series, y: pd.Series) -> tuple[float, float, int]:
    mask = x.notna() & y.notna()
    if mask.sum() < 3:
        return float("nan"), float("nan"), int(mask.sum())
    rho, pval = stats.spearmanr(x[mask], y[mask])
    return float(rho), float(pval), int(mask.sum())


def _boxplot_by_status(df: pd.DataFrame, metric: str, out_path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    order = ["MERGED", "CLOSED"]
    palette = {"MERGED": "#4C9F70", "CLOSED": "#D16B6B"}
    sns.boxplot(
        data=df,
        x="state",
        y=metric,
        order=order,
        hue="state",
        palette=palette,
        legend=False,
        showfliers=False,
        ax=ax,
    )
    ax.set_xlabel("Status do PR")
    ax.set_ylabel(METRIC_LABELS[metric])
    ax.set_title(title)
    if df[metric].min() >= 0 and df[metric].max() > 0:
        ax.set_yscale("symlog")
    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def _scatter_vs_reviews(df: pd.DataFrame, metric: str, out_path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    sample = df.sample(min(len(df), 8000), random_state=42)
    sns.regplot(
        data=sample,
        x=metric,
        y="reviews_count",
        scatter_kws={"alpha": 0.25, "s": 10, "color": "#2C7BB6"},
        line_kws={"color": "#D7191C"},
        ci=None,
        ax=ax,
    )
    ax.set_xlabel(METRIC_LABELS[metric])
    ax.set_ylabel(METRIC_LABELS["reviews_count"])
    ax.set_title(title)
    if metric in {"changed_files", "lines_changed", "analysis_time_hours", "body_length_chars"}:
        if sample[metric].min() > 0:
            ax.set_xscale("log")
    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def _heatmap(df: pd.DataFrame, out_path: Path) -> None:
    cols = [
        "changed_files",
        "lines_changed",
        "analysis_time_hours",
        "body_length_chars",
        "participants_count",
        "comments_count",
        "reviews_count",
    ]
    rename_map = {c: METRIC_LABELS[c] for c in cols}
    corr = df[cols].rename(columns=rename_map).corr(method="spearman")
    fig, ax = plt.subplots(figsize=(9, 7))
    sns.heatmap(
        corr,
        annot=True,
        fmt=".2f",
        cmap="vlag",
        center=0,
        vmin=-1,
        vmax=1,
        square=True,
        cbar_kws={"label": "Correlacao de Spearman"},
        ax=ax,
    )
    ax.set_title("Heatmap de correlacoes (Spearman) entre as metricas")
    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def run_analysis(dataset_path: Path, figures_dir: Path, summary_path: Path) -> dict:
    df = pd.read_csv(dataset_path)
    df["status_bin"] = (df["state"] == "MERGED").astype(int)

    sns.set_theme(style="whitegrid", context="paper")
    _ensure_dirs(figures_dir)

    summary: dict = {
        "n_total": int(len(df)),
        "n_merged": int((df["state"] == "MERGED").sum()),
        "n_closed": int((df["state"] == "CLOSED").sum()),
        "n_repos": int(df["repo"].nunique()),
        "medians_overall": {},
        "medians_by_status": {"MERGED": {}, "CLOSED": {}},
        "rq_results": [],
        "figures": {},
    }

    for metric in METRIC_LABELS:
        summary["medians_overall"][metric] = float(df[metric].median())
    for status in ("MERGED", "CLOSED"):
        sub = df[df["state"] == status]
        for metric in METRIC_LABELS:
            summary["medians_by_status"][status][metric] = float(sub[metric].median())

    for rq, metrics in RQ_STATUS_METRICS.items():
        for metric in metrics:
            rho, pval, n = _spearman(df[metric], df["status_bin"])
            fig_name = f"{rq.lower()}_boxplot_{metric}.png"
            fig_path = figures_dir / fig_name
            _boxplot_by_status(
                df,
                metric,
                fig_path,
                title=f"{rq}: {METRIC_LABELS[metric]} por status do PR",
            )
            summary["rq_results"].append(
                {
                    "rq": rq,
                    "dimension": RQ_DIMENSION_LABELS[rq],
                    "dependent": "status (MERGED=1, CLOSED=0)",
                    "metric": metric,
                    "metric_label": METRIC_LABELS[metric],
                    "spearman_rho": rho,
                    "p_value": pval,
                    "n": n,
                    "median_merged": float(df.loc[df["state"] == "MERGED", metric].median()),
                    "median_closed": float(df.loc[df["state"] == "CLOSED", metric].median()),
                    "figure": fig_name,
                }
            )
            summary["figures"][f"{rq}_{metric}"] = fig_name

    for rq, metrics in RQ_REVIEWS_METRICS.items():
        for metric in metrics:
            rho, pval, n = _spearman(df[metric], df["reviews_count"])
            fig_name = f"{rq.lower()}_scatter_{metric}_vs_reviews.png"
            fig_path = figures_dir / fig_name
            _scatter_vs_reviews(
                df,
                metric,
                fig_path,
                title=f"{rq}: {METRIC_LABELS[metric]} vs numero de revisoes",
            )
            summary["rq_results"].append(
                {
                    "rq": rq,
                    "dimension": RQ_DIMENSION_LABELS[rq],
                    "dependent": "reviews_count",
                    "metric": metric,
                    "metric_label": METRIC_LABELS[metric],
                    "spearman_rho": rho,
                    "p_value": pval,
                    "n": n,
                    "figure": fig_name,
                }
            )
            summary["figures"][f"{rq}_{metric}"] = fig_name

    heatmap_path = figures_dir / "heatmap_correlacoes.png"
    _heatmap(df, heatmap_path)
    summary["figures"]["heatmap"] = "heatmap_correlacoes.png"

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info("Analise concluida. Summary: %s", summary_path)
    return summary


def main() -> dict:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    dataset_path = Path("data/dataset_final.csv")
    if not dataset_path.exists():
        raise FileNotFoundError(
            "data/dataset_final.csv nao encontrado. Rode build_dataset.py antes."
        )
    figures_dir = Path("figures")
    summary_path = Path("data/results_summary.json")
    return run_analysis(dataset_path, figures_dir, summary_path)


if __name__ == "__main__":
    main()
