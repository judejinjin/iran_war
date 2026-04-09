"""
LLM Client — GitHub Copilot SDK backend.

Wraps the async Copilot SDK in a synchronous interface matching LLMClient,
so all existing call sites (simple_prompt / agent_loop) work unchanged.
"""

import asyncio
import json
from loguru import logger

from config import COPILOT_MODEL, COPILOT_MAX_TOKENS


class CopilotLLMClient:
    """Drop-in replacement for LLMClient using the GitHub Copilot SDK."""

    def __init__(self):
        # Import here so the dependency is only required when this backend is active
        try:
            import copilot  # noqa: F401
        except ImportError:
            raise ImportError(
                "github-copilot-sdk is required for the copilot_sdk backend. "
                "Install it with: pip install github-copilot-sdk"
            )
        self.model = COPILOT_MODEL
        self.max_tokens = COPILOT_MAX_TOKENS

    # ── public sync API (matches LLMClient) ──────────────────────────────────

    def simple_prompt(self, system: str, user_prompt: str) -> str:
        """Single-turn prompt without tools."""
        return asyncio.run(self._simple_prompt_async(system, user_prompt))

    def agent_loop(self, system: str, user_prompt: str, tools: list,
                   tool_handlers: dict, max_iterations: int = 10) -> str:
        """
        Tool-use agent loop.

        Accepts Anthropic-format tool schemas + handler dict and converts
        them to Copilot SDK Tool objects internally.
        """
        return asyncio.run(self._agent_loop_async(
            system, user_prompt, tools, tool_handlers, max_iterations
        ))

    def chat(self, system: str, messages: list, tools: list = None,
             max_tokens: int = None):
        """
        Low-level call.  Routes through simple_prompt for the common case.

        Returns a shim object whose .content list matches the Anthropic
        response shape just enough for callers that read text blocks.
        """
        user_msg = messages[-1]["content"] if messages else ""
        text = self.simple_prompt(system, user_msg)
        return _FakeResponse(text)

    # ── async internals ──────────────────────────────────────────────────────

    async def _simple_prompt_async(self, system: str, user_prompt: str) -> str:
        import tempfile
        import shutil
        from copilot import CopilotClient, SubprocessConfig
        from copilot.session import PermissionHandler

        # Run CLI in an empty temp directory so it cannot read project files
        # or use tools productively — forces pure LLM behavior.
        tmpdir = tempfile.mkdtemp(prefix="copilot_llm_")
        try:
            config = SubprocessConfig(cwd=tmpdir)

            async with CopilotClient(config) as client:
                # Prepend a hard constraint to the system message
                full_system = (
                    "IMPORTANT: Do NOT use any tools. Do NOT read, search, or write "
                    "files. Respond with ONLY the requested content directly in your "
                    "message. Never say 'saved to file' or 'classification complete' "
                    "— put the actual content in your response.\n\n"
                    + system
                )
                async with await client.create_session(
                    on_permission_request=PermissionHandler.approve_all,
                    model=self.model,
                    system_message={"content": full_system},
                    infinite_sessions={"enabled": False},
                ) as session:
                    done = asyncio.Event()
                    result_text = ""

                    def on_event(event):
                        nonlocal result_text
                        if event.type.value == "assistant.message":
                            result_text = event.data.content
                        elif event.type.value == "session.idle":
                            done.set()

                    session.on(on_event)
                    await session.send(user_prompt)
                    try:
                        await asyncio.wait_for(done.wait(), timeout=120)
                    except asyncio.TimeoutError:
                        logger.warning("Copilot SDK session timed out after 120s")
                    return result_text
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    async def _agent_loop_async(self, system, user_prompt, tools,
                                tool_handlers, max_iterations) -> str:
        from copilot import CopilotClient
        from copilot.tools import Tool, ToolInvocation, ToolResult
        from copilot.session import PermissionHandler

        # Convert Anthropic tool schemas → Copilot SDK Tool objects
        sdk_tools = []
        for tool_def in tools:
            name = tool_def["name"]
            handler = tool_handlers.get(name)
            sdk_tools.append(Tool(
                name=name,
                description=tool_def.get("description", ""),
                parameters=tool_def.get("input_schema", {}),
                handler=self._make_async_handler(name, handler),
                skip_permission=True,
            ))

        async with CopilotClient() as client:
            async with await client.create_session(
                on_permission_request=PermissionHandler.approve_all,
                model=self.model,
                system_message={"content": system},
                tools=sdk_tools,
                infinite_sessions={"enabled": False},
            ) as session:
                done = asyncio.Event()
                result_text = ""

                def on_event(event):
                    nonlocal result_text
                    if event.type.value == "assistant.message":
                        result_text = event.data.content
                    elif event.type.value == "session.idle":
                        done.set()

                session.on(on_event)
                await session.send(user_prompt)
                await done.wait()
                return result_text

    @staticmethod
    def _make_async_handler(name, sync_handler):
        """Wrap a sync tool handler as an async Copilot SDK tool handler."""
        from copilot.tools import ToolResult

        async def handler(invocation) -> ToolResult:
            if sync_handler is None:
                return ToolResult(
                    text_result_for_llm=f"Unknown tool: {name}",
                    result_type="error",
                )
            try:
                result = sync_handler(invocation.arguments)
                text = json.dumps(result) if not isinstance(result, str) else result
                return ToolResult(
                    text_result_for_llm=text,
                    result_type="success",
                )
            except Exception as e:
                logger.error(f"Tool {name} failed: {e}")
                return ToolResult(
                    text_result_for_llm=f"Error: {e}",
                    result_type="error",
                )
        return handler


# ── Minimal shim so callers expecting response.content work ──────────────────

class _FakeResponse:
    """Mimics Anthropic message response shape for .content text blocks."""
    def __init__(self, text: str):
        self.content = [_TextBlock(text)]


class _TextBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text
