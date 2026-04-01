# SRT Translation Service Specification

A standalone service that accepts an SRT subtitle file in a source language and returns a bilingual SRT file with translations.

## API Contract

```
Input:  SRT file (source language)
Output: Bilingual SRT file (source line 1, translation line 2 per entry)
Config: model_path, batch_size
```

### Input SRT Format (standard)

```
1
00:00:01,000 --> 00:00:03,500
Bonjour, comment ça va?

2
00:00:04,000 --> 00:00:06,200
Je suis très content de vous voir.
```

### Output SRT Format (bilingual)

```
1
00:00:01,000 --> 00:00:03,500
Bonjour, comment ça va?
你好，你怎么样？

2
00:00:04,000 --> 00:00:06,200
Je suis très content de vous voir.
我很高兴见到你。
```

---

## Internal Pipeline

```
Parse SRT → Preprocess → Batch Translate → Validate → Format Bilingual SRT
```

### Step 1: Parse SRT

Parse input into segment objects:

```json
[
  {"id": 1, "start": 1.0, "end": 3.5, "text": "Bonjour, comment ça va?"},
  {"id": 2, "start": 4.0, "end": 6.2, "text": "Je suis très content de vous voir."}
]
```

Timestamp format: `HH:MM:SS,mmm` (standard SRT). Preserve timestamps exactly — they pass through unchanged.

### Step 2: Preprocess

Apply in order:

1. **Filter empties** — Remove segments where text is empty, `...`, or starts with `...`
2. **Sort by id** — Ensure segment order
3. **Regenerate sequential IDs** — Re-number from 1 to fill gaps left by filtering
4. **Convert to translation format** — Extract only `{"id": N, "fr": "text"}` for the LLM

### Step 3: Batch Translate

Divide segments into batches (default: 10 per batch). For each batch:

1. Build context: the last 3 segments *before* the current batch (French text concatenated)
2. Format the prompt (see [Prompt Template](#prompt-template))
3. Send to LLM
4. Validate response (see [Validation](#validation-rules))
5. On failure: recursively split batch in half and retry each half

#### LLM Call

```python
messages = [{"role": "user", "content": prompt}]
formatted = tokenizer.apply_chat_template(messages, add_generation_prompt=True)
response = generate(model, tokenizer, prompt=formatted, max_tokens=2048)
```

**Model config:**
- `temperature`: 0
- `max_tokens`: 2048
- `max_retries`: 1 (per batch/sub-batch)
- `retry_delay`: 1.0s

#### Recursive Split Strategy

```
Batch fails validation
  → Split in half → [batch_a, batch_b]
    → Each half retried independently
      → If half fails, split again
        → Down to single segments
          → Single segment fails after retries → raise error
```

Sub-batch IDs: `batch_01_a`, `batch_01_a_a`, etc.

### Step 4: Merge and Format Output

Map translations back to original segments by id, then format as bilingual SRT:

```
{entry_number}
{start_time} --> {end_time}
{original_text}
{translated_text}
```

If a segment has no translation, output only the original text line.

---

## Prompt Template

The current production prompt (French → Chinese). Adapt `fr`/`zh` fields and language instructions for other language pairs.

```
你是一名专业法语字幕译员，任务是将法语字幕翻译成准确、贴近原句结构的中文，用于语言学习。

翻译规则：

1. 只输出 JSON 数组，格式严格如下：
  [{"id": 1, "zh": "翻译内容"}, ...]

2. 必须保留并按顺序输出所有id： 每一条输出的 id 必须原样复制自输入字幕；
   注意: 输出条目与 原字幕 必须一一对应，禁止跳过、重复或错位；

翻译要求：

1. 尽量直译，保持原句逻辑和语序
2. 中文需通顺，但允许保留轻微"外语感"
3. 可参考【前文提要】理解语境
4. 输出必须是单个完整JSON数组，格式严格为：[{...}, {...}, {...}]，不要分行输出多个数组。

输入示例：
[{"id": 1, "fr": "Et il faut être vraiment fort pour aller jusqu'au bout."}]

输出示例：
[{"id": 1, "zh": "而且要走到最后，真的需要很强"}]

前文提要：
{context}

待处理字幕：
{segments}
```

**Placeholder values:**
- `{context}` — French text of the 3 segments immediately before this batch. Empty string for the first batch.
- `{segments}` — JSON array of current batch: `[{"id": N, "fr": "..."}, ...]`

---

## Validation Rules

Applied to the LLM's raw response string, in order:

### 1. Sanitize Smart Quotes

LLMs sometimes output Unicode smart quotes (`""''`) instead of ASCII quotes. Before JSON parsing, normalize these to standard `"` when they appear in JSON-structural positions (opening/closing string delimiters). Preserve smart quotes that appear *inside* string values.

### 2. Parse JSON

1. Try `json.loads(response)` directly
2. If that fails, extract via regex: `re.search(r'\[.*\]', response, re.DOTALL)` and parse the match
3. If both fail → **validation error**, trigger retry/split

### 3. Structure Validation

- Response must be a JSON array
- Array length must equal input batch length exactly
- Each item must be a dict with `id` (int) and `zh` (string) fields
- Each `id` must match the corresponding input segment's id, in order

### 4. Content Validation

For each translated item, check `zh` value against the original `fr`:

| Condition | Result |
|---|---|
| Empty or whitespace-only | **reject** |
| Contains Chinese characters (`\u4e00-\u9fff`) and differs from original | **accept** |
| Contains Chinese characters but identical to original French | **reject** |
| Numbers/punctuation only (`^[\d\s,.\-:;]+$`) | **accept** (statistical data) |
| ≤3 words, case-insensitive match to French | **accept** (proper noun/name) |
| Different from French (case-insensitive) | **accept** |
| Same as French, >3 words | **reject** |

Any rejection triggers retry/split for the batch.

---

## Error Handling

| Scenario | Behavior |
|---|---|
| JSON parse failure | Retry, then split batch |
| Count mismatch | Retry, then split batch |
| Invalid translation content | Retry, then split batch |
| Single segment fails after all retries | Raise error for that segment |
| Model not available | Fail fast with clear error |

---

## Configuration

```yaml
translation:
  model_path: "mlx-community/Qwen3-4B-Instruct-2507-4bit"
  batch_size: 10
  max_tokens: 2048
  temperature: 0
  max_retries: 1
  retry_delay: 1.0
```

The model and inference layer are currently MLX-based (Apple Silicon). The service can be adapted to any LLM backend — the core logic is: format prompt → call LLM → parse JSON → validate.
