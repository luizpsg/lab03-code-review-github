"""Coleta PRs de cada repositorio com checkpoint idempotente por repo."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm

from src.github_client import GitHubClient

logger = logging.getLogger("lab03.prs")

PRS_PAGE_SIZE = 30

PRS_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(
      states: [MERGED, CLOSED],
      first: %d,
      after: $cursor,
      orderBy: { field: CREATED_AT, direction: DESC }
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        state
        createdAt
        mergedAt
        closedAt
        changedFiles
        additions
        deletions
        bodyText
        participants { totalCount }
        comments { totalCount }
        reviews { totalCount }
      }
    }
  }
  rateLimit { remaining resetAt cost }
}
""" % PRS_PAGE_SIZE


def checkpoint_path(repo_full_name: str, checkpoint_dir: Path) -> Path:
    safe = repo_full_name.replace("/", "__")
    return checkpoint_dir / f"{safe}.json"


def load_checkpoint(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Checkpoint corrompido em %s, recomecando do zero.", path)
        return None


def save_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def collect_prs_for_repo(
    owner: str,
    name: str,
    pr_limit: int,
    client: GitHubClient,
    checkpoint_dir: Path,
) -> list[dict[str, Any]]:
    """Coleta ate `pr_limit` PRs do repositorio, retomando do checkpoint se houver."""
    full_name = f"{owner}/{name}"
    ckpt_path = checkpoint_path(full_name, checkpoint_dir)
    ckpt = load_checkpoint(ckpt_path) or {
        "owner": owner,
        "name": name,
        "cursor": None,
        "done": False,
        "prs": [],
    }

    if ckpt.get("done"):
        return ckpt["prs"]

    cursor = ckpt.get("cursor")
    prs: list[dict[str, Any]] = list(ckpt.get("prs", []))
    pbar = tqdm(
        total=pr_limit,
        initial=min(len(prs), pr_limit),
        desc=f"PRs {full_name}",
        unit="pr",
        leave=False,
    )

    try:
        while len(prs) < pr_limit:
            data = client.run(PRS_QUERY, {"owner": owner, "name": name, "cursor": cursor})
            repo = data.get("repository")
            if not repo:
                logger.warning("Repositorio %s indisponivel, encerrando coleta.", full_name)
                break
            pulls = repo["pullRequests"]
            for node in pulls["nodes"]:
                prs.append(
                    {
                        "repo": full_name,
                        "pr_number": node["number"],
                        "state": node["state"],
                        "created_at": node["createdAt"],
                        "merged_at": node["mergedAt"],
                        "closed_at": node["closedAt"],
                        "changed_files": node["changedFiles"],
                        "additions": node["additions"],
                        "deletions": node["deletions"],
                        "body_length_chars": len(node.get("bodyText") or ""),
                        "participants_count": node["participants"]["totalCount"],
                        "comments_count": node["comments"]["totalCount"],
                        "reviews_count": node["reviews"]["totalCount"],
                    }
                )
                pbar.update(1)
                if len(prs) >= pr_limit:
                    break

            cursor = pulls["pageInfo"]["endCursor"]
            has_next = pulls["pageInfo"]["hasNextPage"]
            ckpt.update({"cursor": cursor, "prs": prs, "done": False})
            save_checkpoint(ckpt_path, ckpt)

            if not has_next:
                break

        ckpt.update({"prs": prs, "done": True})
        save_checkpoint(ckpt_path, ckpt)
        return prs
    finally:
        pbar.close()


def main() -> Path:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

    repos_csv = Path("data/repos.csv")
    if not repos_csv.exists():
        raise FileNotFoundError(
            "data/repos.csv nao encontrado. Rode collect_repos.py antes."
        )
    repos_df = pd.read_csv(repos_csv)

    pr_limit = int(os.getenv("PR_LIMIT_PER_REPO", "200"))
    checkpoint_dir = Path("data/checkpoints")
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    client = GitHubClient()
    all_prs: list[dict[str, Any]] = []

    repo_iter = tqdm(
        list(repos_df.itertuples(index=False)),
        desc="Repositorios",
        unit="repo",
    )
    for repo in repo_iter:
        repo_iter.set_postfix_str(repo.full_name)
        try:
            prs = collect_prs_for_repo(
                owner=repo.owner,
                name=repo.name,
                pr_limit=pr_limit,
                client=client,
                checkpoint_dir=checkpoint_dir,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Falha coletando %s: %s", repo.full_name, exc)
            continue
        all_prs.extend(prs)

    output_path = Path("data/prs_raw.csv")
    pd.DataFrame(all_prs).to_csv(output_path, index=False, encoding="utf-8")
    logger.info("Salvos %d PRs em %s (de %d repos)", len(all_prs), output_path, len(repos_df))
    return output_path


if __name__ == "__main__":
    main()
