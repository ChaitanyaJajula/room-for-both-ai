from openai import OpenAI

from app.core.config import get_settings


def create_chat_completion(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    max_tokens: int = 128,
    timeout: float = 60.0,
    max_retries: int = 1,
) -> str:
    """Send chat messages to Nemotron via the Nebius OpenAI-compatible API; return the text."""
    settings = get_settings()
    if not settings.NEBIUS_API_KEY:
        raise RuntimeError("NEBIUS_API_KEY is not set. Add it to services/api/.env")

    client = OpenAI(
        api_key=settings.NEBIUS_API_KEY,
        base_url=settings.NEBIUS_BASE_URL,
        timeout=timeout,
        max_retries=max_retries,
    )
    response = client.chat.completions.create(
        model=settings.NEMOTRON_FAST_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body={
            "chat_template_kwargs": {
                "enable_thinking": False
            }
        },
    )
    return response.choices[0].message.content or ""


def send_test_message(message: str = "Say hello in one short sentence.") -> str:
    """Send a test message to Nemotron via the Nebius OpenAI-compatible API."""
    return create_chat_completion([{"role": "user", "content": message}], max_tokens=128)


if __name__ == "__main__":
    print(send_test_message())
