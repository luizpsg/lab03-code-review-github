"""Cliente GraphQL para a API do GitHub com tratamento de rate limit e retry."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"

# Quando o orcamento ficar abaixo deste valor, pausa ate o resetAt para evitar bloqueio.
RATE_LIMIT_THRESHOLD = 50

# Politica de retry: pausas em segundos antes de cada nova tentativa.
RETRY_BACKOFF_SECONDS = [1, 2, 4, 8, 16, 32]

# Timeout (segundos) por chamada HTTP.
HTTP_TIMEOUT = 60


logger = logging.getLogger("lab03.github")


class GitHubGraphQLError(RuntimeError):
    """Erro irreparavel ao consultar a API GraphQL do GitHub."""


class GitHubClient:
    """Pequeno wrapper sobre `requests` para falar GraphQL com o GitHub.

    Responsabilidades:
        - autenticacao via token do ambiente;
        - retry exponencial em erros transitorios (HTTP 5xx, timeouts, abuse);
        - respeitar o rate limit do GraphQL, pausando ate `resetAt` quando necessario;
        - paginacao generica por cursor.
    """

    def __init__(self, token: str | None = None, env_path: str | None = None) -> None:
        load_dotenv(env_path)
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token or self.token.startswith("ghp_seu_token"):
            raise GitHubGraphQLError(
                "GITHUB_TOKEN nao definido. Crie um .env com seu Personal Access Token."
            )
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "lab03-code-review-pucminas",
            }
        )

    def run(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Executa uma query GraphQL e devolve `data`. Faz retry e respeita rate limit."""
        payload = {"query": query, "variables": variables or {}}
        last_error: Exception | None = None

        for attempt, backoff in enumerate([0, *RETRY_BACKOFF_SECONDS]):
            if backoff:
                logger.warning(
                    "Retry GraphQL apos erro transitorio em %ss (tentativa %d).",
                    backoff,
                    attempt,
                )
                time.sleep(backoff)
            try:
                response = self.session.post(
                    GITHUB_GRAPHQL_URL, json=payload, timeout=HTTP_TIMEOUT
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_error = exc
                continue

            if response.status_code in (502, 503, 504):
                last_error = GitHubGraphQLError(
                    f"HTTP {response.status_code} (transient): {response.text[:200]}"
                )
                continue

            if response.status_code == 403:
                retry_after = int(response.headers.get("Retry-After", "30"))
                logger.warning(
                    "Recebido HTTP 403 (abuse/secondary rate limit). Aguardando %ss.",
                    retry_after,
                )
                time.sleep(retry_after)
                last_error = GitHubGraphQLError(response.text[:200])
                continue

            if response.status_code >= 400:
                raise GitHubGraphQLError(
                    f"HTTP {response.status_code}: {response.text[:500]}"
                )

            body = response.json()
            if body.get("errors"):
                messages = "; ".join(err.get("message", "?") for err in body["errors"])
                if any(
                    "rate limit" in (err.get("message") or "").lower()
                    for err in body["errors"]
                ):
                    logger.warning("GraphQL rate limit: %s. Pausando 60s.", messages)
                    time.sleep(60)
                    last_error = GitHubGraphQLError(messages)
                    continue
                raise GitHubGraphQLError(f"GraphQL errors: {messages}")

            data = body.get("data") or {}
            rate_limit = data.get("rateLimit")
            if rate_limit:
                self._respect_rate_limit(rate_limit)
            return data

        raise GitHubGraphQLError(
            f"Esgotadas as tentativas de retry. Ultimo erro: {last_error!r}"
        )

    @staticmethod
    def _respect_rate_limit(rate_limit: dict[str, Any]) -> None:
        remaining = rate_limit.get("remaining")
        reset_at = rate_limit.get("resetAt")
        if remaining is None or reset_at is None:
            return
        if remaining > RATE_LIMIT_THRESHOLD:
            return
        reset_dt = datetime.fromisoformat(reset_at.replace("Z", "+00:00"))
        wait_seconds = max(5, int((reset_dt - datetime.now(timezone.utc)).total_seconds()) + 5)
        logger.warning(
            "Rate limit baixo (%d pontos). Aguardando %ss ate %s.",
            remaining,
            wait_seconds,
            reset_at,
        )
        time.sleep(wait_seconds)
