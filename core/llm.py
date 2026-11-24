"""LLM wrapper with three providers:
  - 'mock'                -> offline fake output, for testing the flow
  - 'ollama:<model>'      -> free local model via Ollama (e.g. ollama:qwen2.5:7b)
  - anything else         -> Anthropic API (needs ANTHROPIC_API_KEY)
"""
import json
import os
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

def _ollama(system, user, model, max_tokens, temperature=None):
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
    opts = {"num_predict": max_tokens}
    if temperature is not None:
        opts["temperature"] = temperature
    body = json.dumps({"model": model, "messages": msgs, "stream": False,
                       "options": opts}).encode()
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read())["message"]["content"]
    except OSError as e:
        raise RuntimeError(f"Cannot reach Ollama at {OLLAMA_URL}. Is it running? ({e})")


def complete(system, user, model, max_tokens=1200, temperature=None):
    if model == "mock":
        return "[MOCK OUTPUT] " + user[:200]
    if model.startswith("ollama:"):
        return _ollama(system, user, model.split(":", 1)[1], max_tokens, temperature)
    import anthropic

    client = anthropic.Anthropic()
    kwargs = dict(model=model, max_tokens=max_tokens,
                  messages=[{"role": "user", "content": user}])
    if system:
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    return "".join(b.text for b in resp.content if b.type == "text")


DEFAULT_MODEL = os.environ.get("STUDIO_MODEL", "ollama:qwen2.5:7b")