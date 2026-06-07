# LLM Backends

This project runs **local-first by default**. A 4B-class model on Ollama is the
primary supported path. Cloud models are an opt-in extension.

---

## Supported Backends

| Backend | Config key | When to use |
|---------|-----------|-------------|
| **Ollama** (default) | `llm.backend = "ollama"` | Local, private, works on a 16 GB laptop |
| OpenAI-compatible API | `llm.backend = "openai"` | Cloud fallback or hosted Ollama via OpenAI shim |

---

## Recommended Models

### ✅ Recommended: 4B-class (16 GB laptop, CPU + small GPU)

These models balance triage quality and speed at the 4B parameter scale.

| Model | Pull command | Notes |
|-------|-------------|-------|
| **Llama 3.1 8B** | `ollama pull llama3.1:8b` | Best all-round choice if you have 12+ GB VRAM |
| **Llama 3.2 3B** | `ollama pull llama3.2:3b` | Recommended for 16 GB RAM, CPU-only |
| **Qwen 2.5 3B** | `ollama pull qwen2.5:3b` | Strong instruction-following, low memory |
| **Phi-4 mini** | `ollama pull phi4-mini` | Microsoft, excellent JSON schema adherence |
| **Mistral 7B** | `ollama pull mistral:7b` | Good for longer threads, needs 8 GB VRAM |

### ⚠️ Advanced: 13B+ (requires 24 GB+ VRAM or Apple Silicon)

| Model | Notes |
|-------|-------|
| Llama 3.1 70B (quantised) | Best accuracy, very slow on CPU |
| Mixtral 8x7B | Strong MoE model, high memory |

---

## config.yaml Model Settings

```yaml
llm:
  backend: ollama         # ollama | openai
  model: llama3.2:3b      # Ollama model tag or OpenAI model name
  base_url: http://localhost:11434  # Ollama default; change for remote
  num_ctx: 4096           # Context window. Keep ≤ 8192 for 4B models.
  temperature: 0.1        # Low = more consistent JSON output
  max_batch_tokens: 3000  # Max tokens per LLM batch. Reduce for small models.
```

### Token budget guidance

| Model class | Recommended `num_ctx` | Recommended `max_batch_tokens` |
|-------------|----------------------|--------------------------------|
| 3B          | 2048–4096            | 2000–3000                      |
| 7–8B        | 4096–8192            | 3000–5000                      |
| 13B+        | 8192+                | 5000+                          |

If you see JSON parse errors or truncated outputs, reduce `max_batch_tokens`
first, then `num_ctx`.

---

## Quick Setup (Ollama)

```bash
# 1. Install Ollama: https://ollama.com
# 2. Pull the default model
ollama pull llama3.2:3b

# 3. Verify Ollama is running
curl http://localhost:11434/api/tags

# 4. Run the agent
uv run briefing-agent run
```

---

## Benchmarking Models

Use `scripts/bench_models.py` to compare models on a local test inbox
before committing to one for daily use:

```bash
# Run benchmark across all default models
uv run python scripts/bench_models.py

# Run against a specific fixture file
uv run python scripts/bench_models.py --fixture tests/fixtures/sample_inbox.json

# Compare specific models only
uv run python scripts/bench_models.py --models llama3.2:3b phi4-mini
```

Outputs a Markdown table with accuracy, latency per message, and JSON
parse success rate. Results are also written to `data/bench_results.json`.

---

## Adding a New Backend

1. Create `src/briefing_agent/llm/your_backend.py` implementing `BaseLLMClient`.
2. Add a config key in `config.py`.
3. Register it in `llm/__init__.py`'s `get_llm_client()` factory.
4. Add a row to the table above.
