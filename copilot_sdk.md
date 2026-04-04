# Proposal: GitHub Copilot SDK as LLM Backend

## Summary

Replace the direct Anthropic SDK calls in `agents/llm_client.py` with the **GitHub Copilot SDK** (`github-copilot-sdk`), using the Copilot CLI as the LLM runtime. The Copilot SDK backend and the existing Anthropic backend will be selectable via `.env`. The Copilot SDK backend will be the **default**.

---

## Why Copilot SDK

| Concern | Current (Anthropic SDK) | Copilot SDK |
|---------|------------------------|-------------|
| Auth | Requires `CLAUDE_KEY` (paid API key) | Uses GitHub Copilot subscription via `gh` CLI — no separate API key needed |
| Billing | Per-token Anthropic billing | Included in Copilot subscription (premium request quota) |
| Model access | Claude only | Claude, GPT-4o/5, Gemini, etc. via single SDK |
| Tool orchestration | Hand-rolled `agent_loop` in our code | SDK handles planning + tool invocation natively |
| Maintenance | Must maintain retry/error logic ourselves | SDK manages CLI process lifecycle, retries, context compaction |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  .env: LLM_BACKEND=copilot_sdk  (default)              │
│         LLM_BACKEND=anthropic   (existing)              │
│         COPILOT_MODEL=claude-sonnet-4.5                 │
└────────────────────────┬────────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │  agents/llm_client.py│
              │  get_llm_client()    │
              └──────┬───────┬──────┘
                     │       │
        ┌────────────▼┐  ┌──▼────────────┐
        │ LLMClient   │  │ CopilotLLM    │
        │ (Anthropic)  │  │ (Copilot SDK)  │
        │ unchanged    │  │ new            │
        └─────────────┘  └───────────────┘
                              │
                     JSON-RPC (stdio)
                              │
                   ┌──────────▼──────────┐
                   │  Copilot CLI        │
                   │  (gh auth creds)    │
                   └─────────────────────┘
```

Both backends expose the **same interface** — `simple_prompt()`, `agent_loop()`, `chat()` — so no call-site changes are needed.

---

## .env Configuration

```dotenv
# ─── LLM Backend ─────────────────────────────────────────
# "copilot_sdk" (default) | "anthropic"
LLM_BACKEND=copilot_sdk

# ─── Copilot SDK Settings ────────────────────────────────
# Model for Copilot SDK sessions (default: claude-sonnet-4.5)
COPILOT_MODEL=claude-sonnet-4.5
# Max tokens for Copilot SDK responses (default: 4096)
COPILOT_MAX_TOKENS=4096

# ─── Anthropic Settings (existing, used when LLM_BACKEND=anthropic) ──
CLAUDE_KEY=sk-ant-...
# CLAUDE_MODEL and CLAUDE_MAX_TOKENS remain in config.py
```

`claude-sonnet-4.5` is the Copilot SDK model identifier for Claude Sonnet 4.6 (the same model the project currently uses directly via Anthropic).

---

## Authentication

The Copilot SDK uses the Copilot CLI for auth. Since GitHub CLI (`gh`) is already installed:

1. **`gh auth login`** — the user has already done this.
2. The Copilot CLI reads credentials from `gh` automatically (priority 6 in the auth chain).
3. Alternatively set `GH_TOKEN` or `COPILOT_GITHUB_TOKEN` in `.env` for headless/CI use.

No Anthropic API key is needed when using the Copilot SDK backend.

Auth priority (SDK → CLI):
1. Explicit `github_token` kwarg
2. `COPILOT_GITHUB_TOKEN` env var
3. `GH_TOKEN` env var
4. `GITHUB_TOKEN` env var
5. Stored OAuth credentials from `copilot` CLI login
6. **`gh auth` credentials** ← our default path

---

## Prerequisites

```
pip install github-copilot-sdk
```

The Copilot CLI must also be installed and on PATH:

```
copilot --version
```

(Installation: https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli)

Requires **Python 3.11+** (the Copilot SDK requirement). Our project is already Python 3.11+ per `environment.yml`.

---

## Implementation Plan

### 1. Add config entries (`config.py`)

```python
# ─── LLM Backend ─────────────────────────────────────────
LLM_BACKEND = os.environ.get("LLM_BACKEND", "copilot_sdk")   # "copilot_sdk" | "anthropic"

# ─── Copilot SDK ──────────────────────────────────────────
COPILOT_MODEL = os.environ.get("COPILOT_MODEL", "claude-sonnet-4.5")
COPILOT_MAX_TOKENS = int(os.environ.get("COPILOT_MAX_TOKENS", "4096"))
```

### 2. Create `agents/copilot_llm.py` — the new backend

The Copilot SDK is **async-native** (event-driven, `asyncio`). Our codebase is currently synchronous. The new backend will bridge this using `asyncio.run()` internally so callers don't change.

```python
"""
LLM Client — GitHub Copilot SDK backend.
Wraps the async Copilot SDK in a synchronous interface matching LLMClient.
"""
import asyncio
import json
from loguru import logger
from copilot import CopilotClient, define_tool
from copilot.tools import Tool, ToolInvocation, ToolResult
from copilot.session import PermissionHandler

from config import COPILOT_MODEL, COPILOT_MAX_TOKENS


class CopilotLLMClient:
    """Drop-in replacement for LLMClient using GitHub Copilot SDK."""

    def __init__(self):
        self.model = COPILOT_MODEL
        self.max_tokens = COPILOT_MAX_TOKENS

    # ── simple_prompt ────────────────────────────────────
    def simple_prompt(self, system: str, user_prompt: str) -> str:
        """Single-turn prompt, no tools."""
        return asyncio.run(self._simple_prompt_async(system, user_prompt))

    async def _simple_prompt_async(self, system: str, user_prompt: str) -> str:
        async with CopilotClient() as client:
            async with await client.create_session(
                on_permission_request=PermissionHandler.approve_all,
                model=self.model,
                system_message={"content": system},
                infinite_sessions={"enabled": False},
            ) as session:
                response = await session.send_and_wait(prompt=user_prompt)
                return response.data.content if response else ""

    # ── agent_loop ───────────────────────────────────────
    def agent_loop(self, system: str, user_prompt: str, tools: list,
                   tool_handlers: dict, max_iterations: int = 10) -> str:
        """
        Tool-use agent loop.
        Accepts Anthropic-format tool schemas + handler dict,
        converts to Copilot SDK Tool objects internally.
        """
        return asyncio.run(self._agent_loop_async(
            system, user_prompt, tools, tool_handlers, max_iterations
        ))

    async def _agent_loop_async(self, system, user_prompt, tools,
                                 tool_handlers, max_iterations) -> str:
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
                response = await session.send_and_wait(prompt=user_prompt)
                return response.data.content if response else ""

    @staticmethod
    def _make_async_handler(name, sync_handler):
        """Wrap a sync tool handler as an async Copilot SDK handler."""
        async def handler(invocation: ToolInvocation) -> ToolResult:
            try:
                result = sync_handler(invocation.arguments)
                text = json.dumps(result) if not isinstance(result, str) else result
                return ToolResult(text_result_for_llm=text, result_type="success")
            except Exception as e:
                logger.error(f"Tool {name} failed: {e}")
                return ToolResult(text_result_for_llm=f"Error: {e}", result_type="error")
        return handler

    # ── chat (low-level, for direct callers) ─────────────
    def chat(self, system: str, messages: list, tools: list = None,
             max_tokens: int = None):
        """
        Low-level call. Routes through simple_prompt for the common case.
        Not a 1:1 match with Anthropic response objects — callers using
        raw response.content blocks should use the Anthropic backend.
        """
        user_msg = messages[-1]["content"] if messages else ""
        text = self.simple_prompt(system, user_msg)
        return _FakeResponse(text)


class _FakeResponse:
    """Minimal shim so callers expecting response.content work."""
    def __init__(self, text):
        self.content = [_TextBlock(text)]

class _TextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text
```

### 3. Update `agents/llm_client.py` — factory dispatch

```python
# ── Singleton factory ────────────────────────────────────
_client = None

def get_llm_client():
    """Return the configured LLM client (Copilot SDK or Anthropic)."""
    global _client
    if _client is None:
        from config import LLM_BACKEND
        if LLM_BACKEND == "copilot_sdk":
            from agents.copilot_llm import CopilotLLMClient
            _client = CopilotLLMClient()
        else:
            _client = LLMClient()   # existing Anthropic client
    return _client
```

### 4. Zero changes to call sites

All 8 call sites use `get_llm_client()` and call `.simple_prompt()` or `.agent_loop()`. Since `CopilotLLMClient` exposes the same methods with the same signatures, **no changes** to:

- `agents/geopolitical_agent.py`
- `agents/infrastructure_agent.py`
- `agents/military_agent.py`
- `agents/scenario_agent.py`
- `agents/trading_agent.py`
- `agents/production_scenario_agent.py`
- `analysis/summarizer.py`

### 5. Update `requirements.txt`

```
github-copilot-sdk>=0.2.0
```

---

## Tool Schema Translation

The current agents define tools in **Anthropic format**:

```python
{
    "name": "get_latest_futures",
    "description": "...",
    "input_schema": {
        "type": "object",
        "properties": { ... },
        "required": [ ... ],
    },
}
```

The Copilot SDK `Tool` object uses a nearly identical JSON Schema under `parameters`:

```python
Tool(
    name="get_latest_futures",
    description="...",
    parameters={                        # same JSON Schema
        "type": "object",
        "properties": { ... },
        "required": [ ... ],
    },
    handler=async_handler,
)
```

The `_agent_loop_async` method maps `input_schema` → `parameters` and wraps each sync `tool_handlers[name]` callable into an async handler returning `ToolResult`. This is a mechanical 1:1 translation — no schema redesign required.

---

## Async Considerations

| Aspect | Approach |
|--------|----------|
| Copilot SDK is async | Wrap with `asyncio.run()` in sync methods |
| Scheduler calls are sync | No change — sync wrapper handles it |
| Dash callbacks are sync | No change — same reason |
| Event loop conflicts | `asyncio.run()` creates a fresh loop per call; safe since we never nest |
| Future optimization | Can expose native async methods later for Dash async callbacks |

If the project later adopts async throughout (e.g. `async` Dash callbacks), the `_*_async` methods are already ready.

---

## Copilot SDK Session Lifecycle

Each LLM call:

1. Creates a `CopilotClient` → spawns Copilot CLI subprocess
2. Opens a session with model + system message + tools
3. Sends the user prompt
4. SDK orchestrates tool calls automatically (for `agent_loop`)
5. Returns final assistant message
6. Session + client close (context manager cleanup)

The `infinite_sessions={"enabled": False}` flag is set because our calls are independent single-turn or bounded tool-use loops — we don't need cross-call context compaction.

**Performance note:** Creating a fresh CLI subprocess per call adds ~1-2s overhead. For production, we can optimize by keeping a long-lived `CopilotClient` instance and reusing it across calls. This is a follow-up optimization.

---

## Rate Limits

With a Copilot Pro subscription and Claude Sonnet (High tier):

| Limit | Copilot Pro |
|-------|------------|
| Requests/min | 10 |
| Requests/day | 50 |
| Tokens/request | 8000 in, 4000 out |
| Concurrent | 2 |

This is significantly more constrained than direct Anthropic API access. Mitigations:

1. **Batch where possible** — the unified `classify_batch()` already batches 10 articles per call.
2. **Cache aggressively** — summaries and scenario assessments are already stored in DB.
3. **Fallback to Anthropic** — if rate-limited, can switch `LLM_BACKEND=anthropic` in `.env`.
4. **Opt in to paid GitHub Models** — removes free-tier limits with enterprise billing.

---

## Migration Checklist

- [ ] Install Copilot CLI and verify `copilot --version`
- [ ] Ensure `gh auth login` is complete
- [ ] `pip install github-copilot-sdk`
- [ ] Add `LLM_BACKEND`, `COPILOT_MODEL`, `COPILOT_MAX_TOKENS` to `.env`
- [ ] Add `LLM_BACKEND`, `COPILOT_MODEL`, `COPILOT_MAX_TOKENS` to `config.py`
- [ ] Create `agents/copilot_llm.py`
- [ ] Update `get_llm_client()` in `agents/llm_client.py` to dispatch on backend
- [ ] Update `requirements.txt`
- [ ] Test `simple_prompt` path (classification, summarization)
- [ ] Test `agent_loop` path (scenario assessment, trading agent)
- [ ] Verify both backends work by toggling `LLM_BACKEND`

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Copilot SDK is Public Preview | Breaking API changes possible | Pin version; keep Anthropic backend as fallback |
| Rate limits more restrictive | May throttle during heavy backfill | Use Anthropic backend for backfill; Copilot for live |
| CLI subprocess overhead | ~1-2s per call startup | Optimize with persistent client singleton later |
| `chat()` shim is incomplete | Callers expecting raw Anthropic response objects break | Only `simple_prompt`/`agent_loop` are used; `chat()` is internal |
| Python 3.11+ required | May break older environments | Already satisfied per `environment.yml` |
| `asyncio.run()` nesting | Fails if already inside an event loop | Only called from sync code paths; no nesting occurs |

---

## File Changes Summary

| File | Change |
|------|--------|
| `.env` | Add `LLM_BACKEND`, `COPILOT_MODEL`, `COPILOT_MAX_TOKENS` |
| `config.py` | Add `LLM_BACKEND`, `COPILOT_MODEL`, `COPILOT_MAX_TOKENS` |
| `agents/copilot_llm.py` | **New file** — `CopilotLLMClient` class |
| `agents/llm_client.py` | Update `get_llm_client()` factory to dispatch on `LLM_BACKEND` |
| `requirements.txt` | Add `github-copilot-sdk>=0.2.0` |
| All agent/analysis files | **No changes** |
