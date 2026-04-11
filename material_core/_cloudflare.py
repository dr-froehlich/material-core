"""Cloudflare Workers KV REST client for matctl token commands."""

from __future__ import annotations

import json
import os
from importlib.resources import files
from pathlib import Path
from types import TracebackType
from urllib.parse import quote

import click
import httpx

_ENV_VARS = ("CF_ACCOUNT_ID", "CF_API_TOKEN", "CF_KV_NAMESPACE_ID")


def _parse_env_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            result[key] = value
    return result


def _env_file_path() -> Path:
    return Path(str(files("material_core") / "scripts" / ".env"))


def load_credentials() -> tuple[str, str, str]:
    """Return (account_id, api_token, namespace_id).

    Precedence: process environment, then scripts/.env inside the package.
    Raises ClickException naming the missing variable if any is unset.
    """
    values: dict[str, str] = {}
    for name in _ENV_VARS:
        if os.environ.get(name):
            values[name] = os.environ[name]

    if len(values) < len(_ENV_VARS):
        env_path = _env_file_path()
        if env_path.exists():
            file_values = _parse_env_file(env_path)
            for name in _ENV_VARS:
                if name not in values and file_values.get(name):
                    values[name] = file_values[name]

    for name in _ENV_VARS:
        if not values.get(name):
            raise click.ClickException(
                f"missing Cloudflare credential {name} "
                f"(set it in the environment or in {_env_file_path()})"
            )

    return values["CF_ACCOUNT_ID"], values["CF_API_TOKEN"], values["CF_KV_NAMESPACE_ID"]


class KVClient:
    """Thin sync client for one Cloudflare KV namespace."""

    def __init__(self, account_id: str, api_token: str, namespace_id: str) -> None:
        self._base = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
            f"/storage/kv/namespaces/{namespace_id}"
        )
        self._headers = {"Authorization": f"Bearer {api_token}"}
        self._client: httpx.Client | None = None

    def __enter__(self) -> KVClient:
        self._client = httpx.Client(headers=self._headers, timeout=10.0)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    @property
    def _http(self) -> httpx.Client:
        if self._client is None:
            raise RuntimeError("KVClient must be used as a context manager")
        return self._client

    @staticmethod
    def _encode(key: str) -> str:
        return quote(key, safe="")

    def _fail(self, response: httpx.Response, action: str) -> None:
        raise click.ClickException(
            f"Cloudflare API error during {action} "
            f"(HTTP {response.status_code}): {response.text}"
        )

    def put(self, key: str, value: dict) -> None:
        url = f"{self._base}/values/{self._encode(key)}"
        response = self._http.put(
            url,
            content=json.dumps(value),
            headers={"Content-Type": "application/json"},
        )
        if not response.is_success:
            self._fail(response, f"put {key}")

    def get(self, key: str) -> dict | None:
        url = f"{self._base}/values/{self._encode(key)}"
        response = self._http.get(url)
        if response.status_code == 404:
            return None
        if not response.is_success:
            self._fail(response, f"get {key}")
        try:
            return response.json()
        except ValueError:
            self._fail(response, f"decode {key}")
            return None

    def delete(self, key: str) -> bool:
        url = f"{self._base}/values/{self._encode(key)}"
        response = self._http.delete(url)
        if response.status_code == 404:
            return False
        if not response.is_success:
            self._fail(response, f"delete {key}")
        return True

    def list_keys(self, prefix: str) -> list[str]:
        url = f"{self._base}/keys"
        response = self._http.get(
            url, params={"prefix": prefix, "limit": 1000}
        )
        if not response.is_success:
            self._fail(response, f"list prefix {prefix}")
        payload = response.json()
        return [item["name"] for item in payload.get("result", [])]
