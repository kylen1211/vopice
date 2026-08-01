"""Judge LLM factory for pipecat evals (design §3.4, E4).

The official `judge.eval.service` paths can't reach the 8045 gateway:
`ollama` hardcodes `api_key="ollama"` (gateway rejects it, 403) and `openai`
never accepts a `base_url` override (always hits api.openai.com). This module
is the officially-supported `factory:` escape hatch (`judge.py:162-168`),
reusing the same 3 required env vars as bot.py's LLM service — no new config
surface.

Referenced from an eval scenario as:

    judge:
      eval:
        factory: "judge_factory.judge_llm"
"""

from pipecat.services.openai.llm import OpenAILLMService

from config import load_config


def judge_llm(config: dict) -> OpenAILLMService:
    """Build the judge's LLM service, pointed at the 8045 gateway.

    Args:
        config: The scenario's `judge.eval:` block. Unused — endpoint, key,
            and model come from env (same source as bot.py's LLM service).
    """
    cfg = load_config()
    return OpenAILLMService(
        api_key=cfg.llm_api_key,
        base_url=cfg.llm_base_url,
        settings=OpenAILLMService.Settings(model=cfg.llm_model),
    )
