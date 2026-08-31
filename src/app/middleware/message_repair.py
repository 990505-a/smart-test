"""Middleware that repairs broken tool_calls/tool_result message sequences.

Prevents openai.BadRequestError: 400 "An assistant message with 'tool_calls'
must be followed by tool messages responding to each 'tool_call_id'".

This can happen when the SummarizationMiddleware truncates old messages and
cuts in the middle of a tool_calls/ToolMessage pair, leaving orphaned
AIMessages with tool_calls but no corresponding ToolMessages.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import ResponseT
from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langgraph.typing import ContextT


class MessageRepairMiddleware(AgentMiddleware):
    """Validates and repairs message sequences before LLM calls.

    Scans messages for AIMessages with tool_calls that lack corresponding
    ToolMessage responses. Inserts synthetic ToolMessage(error=...) entries
    to satisfy the API contract.
    """

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> Any:
        messages = request.messages
        if messages:
            repaired = self._repair_messages(messages)
            if repaired is not messages:
                request = request.override(messages=repaired)

        return await handler(request)

    @staticmethod
    def _repair_messages(messages: list[AnyMessage]) -> list[AnyMessage]:
        """Ensure every AIMessage.tool_calls has matching ToolMessage entries.

        Returns the original list if no repair needed, or a new list with
        synthetic ToolMessages inserted where missing.
        """
        # Collect all tool_call_ids that have ToolMessage responses
        answered_ids: set[str] = set()
        for msg in messages:
            if isinstance(msg, ToolMessage):
                answered_ids.add(msg.tool_call_id)

        # Check each AIMessage for unanswered tool_calls
        needs_repair = False
        for msg in messages:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc["id"] not in answered_ids:
                        needs_repair = True
                        break
            if needs_repair:
                break

        if not needs_repair:
            return messages

        # Repair: insert synthetic ToolMessage after each orphaned AIMessage
        repaired: list[AnyMessage] = []
        for msg in messages:
            repaired.append(msg)
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc["id"] not in answered_ids:
                        repaired.append(
                            ToolMessage(
                                content=f"[Error: tool result was lost during context summarization. tool_call_id={tc['id']}]",
                                tool_call_id=tc["id"],
                                status="error",
                            )
                        )
        return repaired
