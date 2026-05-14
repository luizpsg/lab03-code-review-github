"""Coleta a lista dos repositorios mais populares do GitHub e filtra por #PRs."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm

from src.github_client import GitHubClient

logger = logging.getLogger("lab03.repos")

REPOS_PAGE_SIZE = 50

REPOS_QUERY = """
query($cursor: String) {
  search(
    query: "stars:>1 sort:stars-desc",
    type: REPOSITORY,
    first: %d,
    after: $cursor
  ) {
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on Repository {
        nameWithOwner
        owner { login }
        name
        url
        stargazerCount
        primaryLanguage { name }
        pullRequests(states: [MERGED, CLOSED]) { totalCount }
      }
    }
  }
  rateLimit { remaining resetAt cost }
}
""" % REPOS_PAGE_SIZE


def collect_top_repositories(
    target_count: int,
    min_prs: int,
    client: GitHubClient,
) -> pd.DataFrame:
    """Itera a busca por estrelas ate juntar `target_count` repos com `>= min_prs` PRs.

    Estrategia: pagina 50 a 50 ordenado por estrelas decrescentes e filtra na hora.
    Para garantir 200 repos mesmo descartando alguns, vamos ate 6 paginas (300 nos).
    """
    collected: list[dict] = []
    cursor: str | None = None
    seen: set[str] = set()
    max_pages = 10

    with tqdm(total=target_count, desc="Repos elegiveis", unit="repo") as pbar:
        for _ in range(max_pages):
            data = client.run(REPOS_QUERY, {"cursor": cursor})
            search = data["search"]
            for node in search["nodes"]:
                if not node:
                    continue
                full_name = node["nameWithOwner"]
                if full_name in seen:
                    continue
                seen.add(full_name)
                pr_total = node["pullRequests"]["totalCount"]
                if pr_total < min_prs:
                    continue
                collected.append(
                    {
                        "owner": node["owner"]["login"],
                        "name": node["name"],
                        "full_name": full_name,
                        "url": node["url"],
                        "stars": node["stargazerCount"],
                        "language": (node.get("primaryLanguage") or {}).get("name"),
                        "pr_total_merged_closed": pr_total,
                    }
                )
                pbar.update(1)
                if len(collected) >= target_count:
                    break

            if len(collected) >= target_count:
                break
            if not search["pageInfo"]["hasNextPage"]:
                break
            cursor = search["pageInfo"]["endCursor"]

    df = pd.DataFrame(collected[:target_count])
    return df


def main() -> Path:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

    target = int(os.getenv("TOP_REPOS", "200"))
    min_prs = int(os.getenv("MIN_PRS_PER_REPO", "100"))

    output_path = Path("data/repos.csv")
    if output_path.exists():
        logger.info("Arquivo %s ja existe. Pulando coleta de repos.", output_path)
        return output_path

    client = GitHubClient()
    logger.info("Coletando top %d repos com >= %d PRs (MERGED+CLOSED)...", target, min_prs)
    df = collect_top_repositories(target_count=target, min_prs=min_prs, client=client)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8")
    logger.info("Salvos %d repos em %s", len(df), output_path)
    return output_path


if __name__ == "__main__":
    main()
