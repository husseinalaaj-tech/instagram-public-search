def call_ollama(messages: List[Dict], model: str, temperature: float, max_tokens: int, base_url: str = "http://localhost:11434") -> str:
    # First, check if the server is reachable
    try:
        requests.get(base_url, timeout=2)
    except requests.exceptions.ConnectionError:
        raise ConnectionError(
            f"Cannot connect to Ollama at {base_url}. "
            "Make sure Ollama is running (e.g., `ollama serve` or `ollama run <model>`)."
        )
    # Build prompt
    prompt = ""
    for msg in messages:
        if msg["role"] == "user":
            prompt += f"User: {msg['content']}\n"
        elif msg["role"] == "assistant":
            prompt += f"Assistant: {msg['content']}\n"
        else:
            prompt += f"{msg['content']}\n"
    prompt += "Assistant:"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens}
    }
    resp = requests.post(f"{base_url}/api/generate", json=payload, timeout=120)
    if resp.status_code == 200:
        return resp.json()["response"]
    else:
        raise Exception(f"Ollama error: {resp.status_code} - {resp.text}")