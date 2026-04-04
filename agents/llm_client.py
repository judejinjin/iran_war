"""
LLM Client — Anthropic Claude Sonnet 4.6 with tool-use loop and fallback.
"""

import json
import time
from loguru import logger

from config import CLAUDE_KEY, CLAUDE_MODEL, CLAUDE_MAX_TOKENS, OPENAI_KEY


class LLMClient:
    """Wrapper around Anthropic SDK for Claude Sonnet 4.6 with tool-use support."""

    def __init__(self):
        import anthropic
        if not CLAUDE_KEY:
            raise ValueError("CLAUDE_KEY not set in .env")
        self.client = anthropic.Anthropic(api_key=CLAUDE_KEY)
        self.model = CLAUDE_MODEL
        self.max_tokens = CLAUDE_MAX_TOKENS

    def chat(self, system: str, messages: list, tools: list = None,
             max_tokens: int = None) -> dict:
        """
        Single Claude API call. Returns the response message.

        Args:
            system: System prompt string.
            messages: List of message dicts [{"role": "user", "content": "..."}].
            tools: Optional list of Anthropic tool definitions.
            max_tokens: Override default max_tokens.

        Returns:
            Anthropic message response object.
        """
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = self.client.messages.create(**kwargs)
        return response

    def agent_loop(self, system: str, user_prompt: str, tools: list,
                   tool_handlers: dict, max_iterations: int = 10) -> str:
        """
        Full tool-use agent loop.

        Calls Claude → checks for tool_use blocks → executes tool via handler →
        returns result → repeats until Claude produces a text response.

        Args:
            system: System prompt.
            user_prompt: Initial user message.
            tools: List of Anthropic tool schema dicts.
            tool_handlers: Dict mapping tool name → callable(input_dict) → result.
            max_iterations: Max tool-use rounds before forcing stop.

        Returns:
            Final text response from Claude.
        """
        messages = [{"role": "user", "content": user_prompt}]

        for iteration in range(max_iterations):
            response = self.chat(system, messages, tools=tools)

            # Check if response contains tool use
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

            if not tool_use_blocks:
                # Pure text response — we're done
                text_parts = [b.text for b in response.content if b.type == "text"]
                return "\n".join(text_parts)

            # Process tool calls
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for tool_block in tool_use_blocks:
                tool_name = tool_block.name
                tool_input = tool_block.input

                logger.debug(f"Agent tool call: {tool_name}({json.dumps(tool_input)[:200]})")

                handler = tool_handlers.get(tool_name)
                if handler:
                    try:
                        result = handler(tool_input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_block.id,
                            "content": json.dumps(result) if not isinstance(result, str) else result,
                        })
                    except Exception as e:
                        logger.error(f"Tool {tool_name} failed: {e}")
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_block.id,
                            "content": f"Error: {e}",
                            "is_error": True,
                        })
                else:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_block.id,
                        "content": f"Unknown tool: {tool_name}",
                        "is_error": True,
                    })

            messages.append({"role": "user", "content": tool_results})

        logger.warning(f"Agent loop hit max iterations ({max_iterations})")
        return "Analysis incomplete — max iterations reached."

    def simple_prompt(self, system: str, user_prompt: str) -> str:
        """Simple single-turn prompt without tools."""
        response = self.chat(system, [{"role": "user", "content": user_prompt}])
        text_parts = [b.text for b in response.content if b.type == "text"]
        return "\n".join(text_parts)


# Singleton instance
_client = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
