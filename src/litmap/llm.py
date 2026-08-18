from __future__ import annotations

from openai import OpenAI

from litmap.config import Settings


def _client(base_url: str, api_key: str) -> OpenAI:
    return OpenAI(base_url=base_url, api_key=api_key)


def embed_texts(settings: Settings, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    client = _client(settings.embed_base_url, settings.embed_api_key)
    vectors: list[list[float]] = []
    batch_size = 32
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        try:
            response = client.embeddings.create(model=settings.embed_model, input=batch)
            ordered = sorted(response.data, key=lambda item: item.index)
            vectors.extend(item.embedding for item in ordered)
        except Exception:
            for item in batch:
                single = client.embeddings.create(model=settings.embed_model, input=item)
                vectors.append(single.data[0].embedding)
    if len(vectors) != len(texts):
        raise RuntimeError("Число эмбеддингов не совпало с числом текстов.")
    return vectors


def chat_complete(settings: Settings, system: str, user: str) -> str:
    client = _client(settings.llm_base_url, settings.llm_api_key)
    response = client.chat.completions.create(
        model=settings.llm_model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    content = response.choices[0].message.content
    return (content or "").strip()
