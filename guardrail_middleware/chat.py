from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Awaitable, Callable, Sequence

from openai import AsyncOpenAI

from .models import Decision, GuardrailResult, Policy
from .security import SecurityPipeline


class GuardrailBlockedError(PermissionError):
    """Raised when a chat input or output is not approved for delivery."""

    def __init__(self, stage: str, result: GuardrailResult):
        super().__init__(f"Chat {stage} was not approved by the guardrail policy.")
        self.stage = stage
        self.result = result


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class GuardedChatResponse:
    content: str
    input_result: GuardrailResult
    output_result: GuardrailResult


ChatCompletion = Callable[[Sequence[ChatMessage]], str | Awaitable[str]]


class OpenAIChatCompletion:
    """Adapt OpenAI chat completions to the GuardedChatClient contract."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout_seconds: float = 30.0,
    ):
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)
        self._model = model

    async def __call__(self, messages: Sequence[ChatMessage]) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": message.role, "content": message.content} for message in messages],
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("OpenAI returned an empty chat completion.")
        return content


class GuardedChatClient:
    """Provider-neutral chat orchestration with input and output enforcement."""

    def __init__(
        self,
        completion: ChatCompletion,
        policy: Policy,
        security_pipeline: SecurityPipeline,
    ):
        self.completion = completion
        self.policy = policy
        self.security_pipeline = security_pipeline

    async def complete(self, messages: Sequence[ChatMessage]) -> GuardedChatResponse:
        user_text = "\n".join(message.content for message in messages if message.role == "user")
        input_result = self.security_pipeline.evaluate(
            user_text,
            self.policy,
            required_semantic_check=True,
        )
        self._require_allow("input", input_result)

        output = self.completion(messages)
        if inspect.isawaitable(output):
            output = await output
        if not isinstance(output, str) or not output.strip():
            raise ValueError("Chat completion returned empty or invalid content.")

        output_result = self.security_pipeline.evaluate(
            output,
            self.policy,
            required_semantic_check=True,
        )
        self._require_allow("output", output_result)
        return GuardedChatResponse(output, input_result, output_result)

    @staticmethod
    def _require_allow(stage: str, result: GuardrailResult) -> None:
        if result.decision != Decision.ALLOW or not result.authorized:
            raise GuardrailBlockedError(stage, result)
