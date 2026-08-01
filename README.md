# voice-agent

A Pipecat AI voice agent built with a cascade pipeline (STT → LLM → TTS).

## Configuration

- **Bot Type**: Web
- **Transport(s)**: SmallWebRTC
- **Pipeline**: Cascade
  - **STT**: Whisper (Local)
  - **LLM**: OpenAI
  - **TTS**: Kokoro

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
   # Edit .env and add your API keys
   ```

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
# In another terminal:
uv run pipecat eval run evals/starter_text.yaml -v    # fast text-mode check
uv run pipecat eval run evals/starter_audio.yaml -v   # full audio round trip (local models, no API keys)
```

`eval:` criteria are scored by a judge LLM — a local Ollama by default (`ollama pull gemma2:9b`). The comments in the scenario files cover the schema and how to use an OpenAI judge instead.

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
├── server/              # Python bot server
│   ├── bot.py           # Main bot implementation
│   ├── evals/           # Behavioral eval scenarios
│   ├── pyproject.toml   # Python dependencies
│   ├── env.example      # Environment variables template
│   ├── .env             # Your API keys (git-ignored)
│   └── ...
├── client/              # React application
│   ├── src/             # Client source code
│   ├── package.json     # Node dependencies
│   └── ...
├── .gitignore           # Git ignore patterns
└── README.md            # This file
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