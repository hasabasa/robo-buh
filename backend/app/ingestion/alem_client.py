"""Клиент Alem Plus (грант Астана Хаб) — OpenAI-совместимый шлюз.

Портировано и обобщено из cube-translator (core/llm_client.py, авторский движок владельца):
async, failover между провайдерами, обработка thinking mode Qwen 3.6
(reasoning_content vs content). Здесь добавлена явная поддержка vision (base64).

⚠️ Vision у Alem работает ТОЛЬКО через data:image/...;base64 — внешние URL дают 403.
⚠️ У Qwen 3.6 thinking mode: при структурном разборе ставить max_tokens ≥ 3000.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class AlemProvider:
    model: str
    api_key: str
    base_url: str = "https://llm.alem.ai/v1"
    max_tokens: int = 4000
    temperature: float = 0.2
    disable_thinking: bool = False


@dataclass
class AlemResponse:
    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    reasoning: str | None = None


class AlemClient:
    """Один или несколько провайдеров с failover: при сбое первого идём к следующему."""

    def __init__(self, providers: list[AlemProvider], timeout: float = 90.0,
                 failover_timeout: float = 45.0):
        if not providers:
            raise ValueError("AlemClient: нужен хотя бы один провайдер")
        self._providers = providers
        self._timeout = timeout
        self._failover_timeout = failover_timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AlemClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    @staticmethod
    def image_data_url(image_bytes: bytes, mime: str = "image/png") -> str:
        """bytes → data:image/png;base64,... (единственный формат, который Alem принимает)."""
        return f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        images: list[str] | None = None,   # список data-URL (vision)
        provider_index: int = 0,
        max_retries: int = 2,
    ) -> AlemResponse:
        """Чат-комплишн с failover. images → мультимодальный user-контент."""
        last_error: Exception | None = None
        for attempt in range(max_retries):
            for i in range(len(self._providers)):
                idx = (provider_index + i) % len(self._providers)
                provider = self._providers[idx]
                is_failover = i > 0 or attempt > 0
                try:
                    return await self._call(
                        provider, system_prompt, user_prompt, images,
                        timeout=self._failover_timeout if is_failover else self._timeout,
                    )
                except Exception as e:  # noqa: BLE001 — пробуем следующего провайдера
                    last_error = e
                    continue
        raise RuntimeError(
            f"Alem: все провайдеры упали после {max_retries} попыток. "
            f"Последняя ошибка: {type(last_error).__name__}: {last_error}"
        )

    async def embed(self, texts: list[str], *, model: str, api_key: str) -> list[list[float]]:
        """Эмбеддинги через /v1/embeddings (модель text-1024, 1024-мерн., нормализованные)."""
        resp = await self._client.post(
            f"{self._providers[0].base_url}/embeddings",
            json={"model": model, "input": texts},
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return [d["embedding"] for d in resp.json()["data"]]

    async def _call(
        self,
        provider: AlemProvider,
        system_prompt: str,
        user_prompt: str,
        images: list[str] | None,
        timeout: float,
    ) -> AlemResponse:
        if images:
            user_content: Any = [{"type": "text", "text": user_prompt}]
            for url in images:
                user_content.append({"type": "image_url", "image_url": {"url": url}})
        else:
            user_content = user_prompt

        payload: dict[str, Any] = {
            "model": provider.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": provider.max_tokens,
            "temperature": provider.temperature,
        }
        if provider.disable_thinking:
            payload["chat_template_kwargs"] = {"enable_thinking": False}

        headers = {
            "Authorization": f"Bearer {provider.api_key}",
            "Content-Type": "application/json",
        }
        start = time.monotonic()
        resp = await self._client.post(
            f"{provider.base_url}/chat/completions", json=payload,
            headers=headers, timeout=timeout,
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"Alem error: {data['error']}")

        msg = data["choices"][0]["message"]
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or (
            msg.get("provider_specific_fields", {}) or {}
        ).get("reasoning")
        usage = data.get("usage", {})
        return AlemResponse(
            content=content.strip(),
            model=provider.model,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            duration_ms=duration_ms,
            reasoning=reasoning,
        )
