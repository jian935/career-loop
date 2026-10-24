# LLM providers: what to use, and how to plug it in

Career-Loop only needs an **OpenAI-compatible** `chat/completions` endpoint.
Switching providers = changing three environment variables; no code change.

```bash
career-loop doctor    # shows whether the key is detected and which model is used
```

## 0. Recommended order

| Situation | Provider | Model | Cost |
| --- | --- | --- | --- |
| Just try the LLM path | **智谱 GLM-4-Flash** | `glm-4-flash` | **free** |
| Free + more models to compare | **SiliconFlow** | `Qwen/Qwen3-8B`, `THUDM/GLM-4-9B-0414` | free tier + ¥16 credit |
| Best quality/price for Chinese | **DeepSeek** | `deepseek-flash` | ~¥1.5–3 in / ¥4.5–9 out per 1M |
| Already on Alibaba Cloud | 百炼 Qwen | `qwen-plus` / `qwen-turbo` | free quota |
| Already on Volcengine | 方舟豆包 | endpoint id | daily free quota |
| Offline / privacy | Ollama | `qwen2.5:7b` | free (local GPU/RAM) |

For this project a small, fast, JSON-capable model is enough. Do **not** pay for a
frontier reasoning model to extract requirements.

## 1. 智谱 GLM-4-Flash (free, recommended first)

```bash
export OPENAI_API_KEY=你的智谱Key
export OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
export OPENAI_MODEL=glm-4-flash
career-loop doctor
```

- Free tier is rate-limited; add retry/backoff if you batch. A `429` means slow down.
- Chinese quality is good for JD parsing; JSON is usually reliable, and the engine
  falls back to rules if parsing fails.

## 2. SiliconFlow (free models + credit)

```bash
export OPENAI_API_KEY=你的硅基流动Key
export OPENAI_BASE_URL=https://api.siliconflow.cn/v1
export OPENAI_MODEL=Qwen/Qwen3-8B
```

- Free models rotate; check the model list in the console before pinning one.
- Requires a Chinese phone number for registration; new users get a small credit.
- Low latency inside mainland China.

## 3. DeepSeek Flash (cheap paid)

```bash
export OPENAI_API_KEY=你的DeepSeekKey
export OPENAI_BASE_URL=https://api.deepseek.com
export OPENAI_MODEL=deepseek-flash
```

Pricing (CNY per 1M tokens, 2026-08 schedule; off-peak / peak):

| | Cache hit | Cache miss | Output |
| --- | ---: | ---: | ---: |
| deepseek-flash | 0.05 / 0.10 | 1.5 / 3.0 | 4.5 / 9.0 |

Peak = 09:00–12:00 and 14:00–18:00 Beijing time; off-peak is half price.

A typical JD + profile run is ~1–2k input tokens and ~1k output:
roughly **¥0.005–0.01 per run**. 100 JDs is about **¥0.5–1**.

## 4. 阿里云百炼 Qwen

```bash
export OPENAI_API_KEY=你的DashScopeKey
export OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
export OPENAI_MODEL=qwen-plus
```

New accounts usually get a free quota; check the console for the current amount.

## 5. 火山方舟 豆包

```bash
export OPENAI_API_KEY=你的方舟Key
export OPENAI_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
export OPENAI_MODEL=你的推理接入点ID
```

The model id is an **endpoint id**, not a public model name; create one in the
console first. There is a daily free quota.

## 6. Ollama (local, no key)

```bash
ollama pull qwen2.5:7b
export OPENAI_API_KEY=ollama
export OPENAI_BASE_URL=http://127.0.0.1:11434/v1
export OPENAI_MODEL=qwen2.5:7b
```

Free and private, but slower and weaker on long JDs. Needs ~8 GB RAM for a 7B
model. Good for offline demos, not for the benchmark.

## Security

- **Never commit a key.** Use environment variables or a local `.env` that is
  gitignored; do not paste keys into issues or chat logs.
- If a key was exposed, rotate it immediately.
- `doctor` only reports **whether** a key is present; it never prints the value.
- Responses are cached locally at `~/.career_loop/llm_cache`; clear it if you
  switch models or prompts. `CAREER_LOOP_NO_CACHE=1` disables caching.

## Notes on quality

- Rule baseline: deterministic, offline, no cost. Use it for regression tests.
- LLM: better on paraphrased / implicit requirements, but may hallucinate. The
  engine requires JSON, validates keys, and falls back to rules on failure.
- Evidence is still a quote from your profile; the LLM is told not to invent it.
