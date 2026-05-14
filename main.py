"""Orquestra o pipeline completo do LAB03 na ordem correta."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from src import analysis, build_dataset, collect_prs, collect_repos, report_builder


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s %(levelname)s %(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def banner(msg: str) -> None:
    line = "=" * 72
    print(f"\n{line}\n{msg}\n{line}")


def main() -> int:
    load_dotenv()
    setup_logging()

    env_token_present = bool(
        (Path(".env").exists() and "GITHUB_TOKEN" in Path(".env").read_text(encoding="utf-8"))
        or (Path(".env").exists() and Path(".env").read_text(encoding="utf-8").strip())
    )
    if not Path(".env").exists():
        print(
            "[ERRO] .env nao encontrado. Copie .env.example -> .env e preencha GITHUB_TOKEN."
        )
        return 1
    _ = env_token_present

    started = time.time()

    banner("ETAPA 1/5 -- Coleta dos repositorios mais populares")
    collect_repos.main()

    banner("ETAPA 2/5 -- Coleta de PRs por repositorio (checkpoint idempotente)")
    collect_prs.main()

    banner("ETAPA 3/5 -- Construcao do dataset final (filtros)")
    build_dataset.main()

    banner("ETAPA 4/5 -- Analise estatistica + figuras")
    analysis.main()

    banner("ETAPA 5/5 -- Geracao do relatorio LaTeX")
    report_builder.main()

    elapsed = time.time() - started
    minutes = elapsed / 60.0
    banner(f"Pipeline concluido em {minutes:.1f} minutos.")
    print("Saidas geradas:")
    print("  - data/repos.csv")
    print("  - data/prs_raw.csv")
    print("  - data/dataset_final.csv")
    print("  - data/results_summary.json")
    print("  - figures/*.png")
    print("  - report/relatorio.tex")
    print("\nPara compilar o PDF (precisa de LaTeX instalado):")
    print("  cd report && latexmk -pdf relatorio.tex")
    print("Sem LaTeX local? Suba relatorio.tex e a pasta figures/ no Overleaf.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
