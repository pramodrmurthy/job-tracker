"""OpenAI access (personal account key from .env). Everything takes an `ask(prompt) -> str` callable so tests can fake it."""

from typing import Callable

from . import config

Ask = Callable[[str], str]


class LLMError(Exception):
    pass


def key_is_set() -> bool:
    return bool(config.load_env().get("OPENAI_API_KEY"))


def make_ask(model: str) -> Ask:
    key = config.load_env().get("OPENAI_API_KEY")
    if not key:
        raise LLMError("OPENAI_API_KEY is missing. Add it to .env in the project folder.")
    from openai import OpenAI
    client = OpenAI(api_key=key)

    def ask(prompt: str) -> str:
        try:
            resp = client.chat.completions.create(model=model, temperature=0,
                                                  messages=[{"role": "user", "content": prompt}])
        except Exception as e:  # network, auth, rate limit: surface a short message, never the key
            raise LLMError(f"OpenAI request failed: {type(e).__name__}: {str(e)[:200]}") from e
        return resp.choices[0].message.content or ""

    return ask
