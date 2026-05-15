"""Aplica os filtros do enunciado e produz o dataset final usado nas analises."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger("lab03.dataset")


def _parse_dt(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True)


def build_dataset(prs_raw_path: Path, output_path: Path) -> pd.DataFrame:
    df = pd.read_csv(prs_raw_path)

    df["created_at"] = _parse_dt(df["created_at"])
    df["merged_at"] = _parse_dt(df["merged_at"])
    df["closed_at"] = _parse_dt(df["closed_at"])

    end_time = df["merged_at"].where(df["state"] == "MERGED", df["closed_at"])
    df["analysis_time_hours"] = (end_time - df["created_at"]).dt.total_seconds() / 3600.0

    df["lines_changed"] = df["additions"].fillna(0) + df["deletions"].fillna(0)

    before = len(df)
    df = df[df["state"].isin(["MERGED", "CLOSED"])]
    df = df[df["reviews_count"] >= 1]
    df = df[df["analysis_time_hours"] > 1]
    df = df.dropna(
        subset=[
            "changed_files",
            "additions",
            "deletions",
            "participants_count",
            "comments_count",
            "reviews_count",
            "analysis_time_hours",
        ]
    )

    keep_cols = [
        "repo",
        "pr_number",
        "state",
        "changed_files",
        "additions",
        "deletions",
        "lines_changed",
        "analysis_time_hours",
        "body_length_chars",
        "participants_count",
        "comments_count",
        "reviews_count",
    ]
    df = df[keep_cols].reset_index(drop=True)

    logger.info("Dataset final: %d PRs (descartados %d).", len(df), before - len(df))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8")
    return df


def main() -> Path:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    prs_raw_path = Path("data/prs_raw.csv")
    if not prs_raw_path.exists():
        raise FileNotFoundError(
            "data/prs_raw.csv nao encontrado. Rode collect_prs.py antes."
        )
    output_path = Path("data/dataset_final.csv")
    build_dataset(prs_raw_path, output_path)
    return output_path


if __name__ == "__main__":
    main()
