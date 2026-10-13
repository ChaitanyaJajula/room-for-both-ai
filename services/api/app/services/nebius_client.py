from openai import OpenAI

from app.core.config import get_settings


def send_test_message(message: str = "Say hello in one short sentence.") -> str:
    """Send a test message to Nemotron via the Nebius OpenAI-compatible API."""
    settings = get_settings()
    if not settings.NEBIUS_API_KEY:
        raise RuntimeError("NEBIUS_API_KEY is not set. Add it to services/api/.env")

    client = OpenAI(api_key=settings.NEBIUS_API_KEY, base_url=settings.NEBIUS_BASE_URL)
    response = client.chat.completions.create(
        model=settings.NEMOTRON_FAST_MODEL,
        messages=[{"role": "user", "content": message}],
        max_tokens=128,
        extra_body={
            "chat_template_kwargs": {
                "enable_thinking": False
            }
        },
    )
    return response.choices[0].message.content or ""


if __name__ == "__main__":
    print(send_test_message())
