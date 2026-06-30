import json
from typing import Any
from google import genai
from app.config import GEMINI_API_KEY, GEMINI_CHAT_MODEL, GEMINI_EMBEDDING_MODEL

client = genai.Client(api_key=GEMINI_API_KEY)

def generateText(prompt: str, temperature: float = 0.2) -> str:
    response = client.models.generate_content(
        model=GEMINI_CHAT_MODEL,
        contents=prompt,
    )

    return response.text or ""

def createEmbedding(textValue: str) -> list[float]:
    result = client.models.embed_content(
        model=GEMINI_EMBEDDING_MODEL,
        contents=textValue,
    )

    embedding = result.embeddings[0]

    if hasattr(embedding, "values"):
        return list(embedding.values)

    if isinstance(embedding, dict) and "values" in embedding:
        return embedding["values"]

    raise ValueError("Could not read embedding values from Gemini response")

def toPgVector(values: list[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"

def parseJsonObject(rawText: str) -> dict[str, Any]:
    cleaned = rawText.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned.replace("```json", "", 1).strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```", "", 1).strip()

    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()

    try:
        return json.loads(cleaned)
    except Exception:
        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start >= 0 and end > start:
            return json.loads(cleaned[start:end + 1])

        raise

def cleanAssistantText(textValue: str) -> str:
    cleaned = textValue or ""

    replacements = {
        "**": "",
        "__": "",
        "### ": "",
        "## ": "",
        "# ": "",
        "`": "",
    }

    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)

    lines = []

    for line in cleaned.splitlines():
        stripped = line.strip()

        if stripped.startswith("*   "):
            stripped = "- " + stripped[4:]

        elif stripped.startswith("* "):
            stripped = "- " + stripped[2:]

        elif stripped.startswith("• "):
            stripped = "- " + stripped[2:]

        lines.append(stripped if stripped else "")

    cleaned = "\n".join(lines)

    while "\n\n\n" in cleaned:
        cleaned = cleaned.replace("\n\n\n", "\n\n")

    return cleaned.strip()