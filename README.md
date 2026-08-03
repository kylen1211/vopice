# voice-agent

A Pipecat AI voice agent built with a cascade pipeline (STT → LLM → TTS).
This is the R6-B P1 voice loop for the personal AI assistant project
(`voice-translate-v2`'s 语音快脑层) — a standalone dogfood/PoC scope: real-time
voice conversation only, no task dispatch, no memory, no multi-agent routing.
Built almost entirely from the official `pipecat init` scaffold; the only
custom pieces are `server/config.py`, `server/prompts.py`,
`server/judge_factory.py`, and `scripts/check_frozen_repo.sh`.

## Quick start (three commands, three terminals)

```bash
cd server && uv run bot.py       # 1. server (STT/LLM/TTS pipeline)
cd client && npm run dev         # 2. front end, http://localhost:5173
cd server && uv run pytest       # 3. unit tests (self-authored modules only)
```

STT (Soniox) and TTS (ElevenLabs) are cloud services requiring paid API keys —
this is no longer the local-CPU/zero-paid-keys setup the project started with.

Requires the 8 required env vars (§"Configure environment variables" below)
to be set to real, non-placeholder values — the server refuses to start if
any of them is missing (fails fast, lists what's missing). This checks
*presence*, not *reachability*: if the values are present but the gateway
itself isn't actually running, the server still starts — the first LLM call
will just fail (non-fatal, logged; see the known-gaps note in §13 of
`openspec/changes/pipecat-native-p1/design.md` for what's and isn't
surfaced to the user when that happens).

## Configuration

- **Bot Type**: Web
- **Transport(s)**: SmallWebRTC
- **Pipeline**: Cascade
  - **STT**: Soniox (Cloud, API key required)
  - **LLM**: OpenAI
  - **TTS**: ElevenLabs (Cloud, API key required)

## Setup

### Server

1. **Navigate to server directory**:

   ```bash
   cd server
   ```

2. **Install dependencies**:

   ```bash
   uv sync
   ```

3. **Configure environment variables**:

   ```bash
   cp .env.example .env
   # Edit .env — see the required variables below
   ```

   Required (server refuses to start if any is missing or left as a
   `CHANGE_ME_*` placeholder — `config.py` reports the full list at once):

   | Variable | Purpose |
   |---|---|
   | `LLM_BASE_URL` | Local OpenAI-compatible gateway URL (1 期: `:8045`) |
   | `LLM_API_KEY` | Gateway key |
   | `LLM_MODEL` | 快脑 model name the gateway routes to |
   | `SLOW_LLM_MODEL` | 慢脑 model name the gateway routes to — deliberately a slower/deeper model than `LLM_MODEL` (see `openspec/changes/fast-slow-brain/design.md` §6.2) |
   | `SONIOX_API_KEY` | Soniox (STT) API key — cloud service, requires a paid account |
   | `ELEVENLABS_API_KEY` | ElevenLabs (TTS) API key — cloud service, requires a paid account |
   | `ELEVENLABS_VOICE_ID` | ElevenLabs voice ID to use for TTS output |
   | `ELEVENLABS_MODEL` | ElevenLabs TTS model name, e.g. `eleven_flash_v2_5` |

   STT (Soniox) and TTS (ElevenLabs) are both cloud services that need a
   reachable API and a paid key — not the local-CPU Whisper/Kokoro setup
   this project started with. Soniox is configured with
   `language_hints=[Language.ZH]` and ElevenLabs with `language=Language.ZH`
   (see `bot.py`). Whether the multi-sentence playback overlap tracked in
   `docs/backlog.md` B2 (root-caused against the old Kokoro/local-CPU TTS)
   still reproduces under ElevenLabs is **unverified** — pending the 第9组
   M3 manual dogfood re-check; do not treat B2 as resolved or as still
   applicable until that re-check lands.

4. **Run the bot**:

   ```bash
   uv run bot.py
   ```

   The runner serves every transport; the caller selects which one (a web/mobile
   client picks its transport when it connects; a telephony provider connects to
   `/ws`).

## Testing with evals

This project includes behavioral evals: scripted conversations that drive the bot headless — no live call needed. Starter scenarios live in `server/evals/`; edit them as your bot takes shape and copy them to add more.

From `server/`, run the bot with the eval transport, then drive scenarios against it from a second terminal (the bot stays up across runs):

```bash
uv run bot.py -t eval
# In another terminal — this project's actual gate set (`pipecat eval run`
# takes individual scenario files, not a directory):
uv run pipecat eval run evals/smoke.yaml -v                     # deterministic link-check (text_contains, no judge)
uv run pipecat eval run evals/r4_no_false_completion.yaml -v    # see judge setup below
uv run pipecat eval run evals/r4_knowledge_qa.yaml -v           # see judge setup below
```

Two more scenarios ship from the scaffold, `evals/starter_text.yaml` and
`evals/starter_audio.yaml` — they use the official default Ollama judge
(`ollama pull gemma2:9b`), which this project doesn't install (see below),
so they aren't part of this project's gate and will fail judge setup as-is.

`eval:` criteria are scored by a judge LLM — a local Ollama by default (`ollama pull gemma2:9b`). We don't run Ollama; `evals/r4_*.yaml` point `judge.eval.factory` at `judge_factory.judge_llm`, which reuses the same gateway as the bot's own LLM (the official `ollama`/`openai` judge paths can't reach it — see `judge_factory.py`). Because the `pipecat` CLI is a separately-installed global tool, not this project's venv, running the `factory:` judge needs the project on `PYTHONPATH` and the 3 `LLM_*` vars pre-exported in the shell (not auto-loaded from `.env` the way `bot.py` does it):

```bash
set -a && source .env && set +a
PYTHONPATH="$(pwd)" pipecat eval run evals/r4_no_false_completion.yaml -v
PYTHONPATH="$(pwd)" pipecat eval run evals/r4_knowledge_qa.yaml -v
```

Each distinct eval measurement should run against a freshly-started `bot.py -t eval` — the eval transport keeps one `LLMContext` for the whole process lifetime (by design, so you can "leave it running and re-run evals as you edit"), so repeated runs against the same process accumulate turns onto each other rather than starting clean.

### R6: verify the old repo stayed frozen

`voice-translate-v2` must stay untouched outside its own `openspec/changes/pipecat-native-p1/**` for as long as this project is implemented there:

```bash
./scripts/check_frozen_repo.sh
```

### Client

1. **Navigate to client directory**:

   ```bash
   cd client
   ```

2. **Install dependencies**:

   ```bash
   npm install
   ```

3. **Configure environment variables**:

   ```bash
   cp env.example .env.local
   # Edit .env.local if needed (defaults to localhost:7860)
   ```

   > **Note:** Environment variables in Vite are bundled into the client and exposed in the browser. For production applications that require secret protection, consider implementing a backend proxy server to handle API requests and manage sensitive credentials securely.

4. **Run development server**:

   ```bash
   npm run dev
   ```

5. **Open browser**:

   http://localhost:5173

## Project Structure

```
voice-agent/
├── server/                  # Python bot server
│   ├── bot.py               # Pipeline assembly (scaffold + 5 authorized edit points, see design.md §5.1)
│   ├── config.py            # [added] startup env validation, fail-fast
│   ├── prompts.py           # [added] system prompt (official + capability-boundary + language sections)
│   ├── judge_factory.py     # [added] points eval judge LLM at our gateway
│   ├── evals/               # Behavioral eval scenarios (starter_* + smoke + r4_*)
│   ├── tests/                # Unit tests for config.py
│   ├── pyproject.toml       # Python dependencies
│   ├── .env.example         # Environment variables template
│   ├── .env                 # Your real values (git-ignored)
│   └── ...
├── client/                  # React application (voice-ui-kit), scaffold + 1 config edit
│   ├── src/config.ts        # [1-line edit] enableDefaultIceServers: false (local/LAN-only, no public STUN)
│   ├── src/                 # Client source code
│   ├── package.json         # Node dependencies
│   └── ...
├── scripts/
│   └── check_frozen_repo.sh # [added] R6: verifies voice-translate-v2 stayed frozen
├── .gitignore                # Git ignore patterns
└── README.md                 # This file
```
## Building with an AI coding agent

Extending this bot with Claude Code, Codex, or another AI coding assistant? Give it live, accurate Pipecat context instead of stale training data with the **Pipecat Context Hub** — a local index of Pipecat docs, examples, and API source your agent queries over MCP:

```bash
# Build the local index (first run takes a couple of minutes)
uvx pipecat-ai-context-hub@latest refresh

# Add it to your agent (use the line for the one you use)
claude mcp add pipecat-context-hub -- uvx pipecat-ai-context-hub serve   # Claude Code
codex mcp add pipecat-context-hub -- uvx pipecat-ai-context-hub serve    # Codex
```

MCP servers load at session start, so add it before opening your coding session. See the [Pipecat Context Hub docs](https://docs.pipecat.ai/api-reference/context-hub) for the full setup.

## Learn More

- [Pipecat Documentation](https://docs.pipecat.ai/)
- [Voice UI Kit Documentation](https://voiceuikit.pipecat.ai/)
- [Pipecat GitHub](https://github.com/pipecat-ai/pipecat)
- [Pipecat Examples](https://github.com/pipecat-ai/pipecat-examples)
- [Discord Community](https://discord.gg/pipecat)