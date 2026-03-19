# Spec: Stage 3 — Date Extraction
slug: s3-dates
layer: stages
phase: 1
arch_section: §6 Stage Implementations; §3.1 REQUIREMENTS (content_age → review_after rules)

---

## Problem statement

After Stage 2 assigns `content_age`, the pipeline needs a resolved `source_date` and a
computed `review_after` deadline attached to the `NormalizedItem` before summarisation
begins. Stage 3 is pure Python logic — no LLM, no vault writes:

1. Resolve the best available `source_date` from three priority tiers.
2. Compute `review_after` from `content_age` rules (REQUIREMENTS §3.1).
3. Return an enriched copy of the `NormalizedItem` via `model_copy`.

---

## Module contract

```
Input:  item:           NormalizedItem         — from agent.core.models
        classification: ClassificationResult   — from agent.core.models

Output: NormalizedItem
          .source_date              set (date | None)
          .extra_metadata["review_after"]  set (ISO string YYYY-MM-DD)
```

Call signature (matches pipeline.py §5):
```python
async def run(
    item: NormalizedItem,
    classification: ClassificationResult,
) -> NormalizedItem
```

---

## Key implementation notes

### 1. Date resolution — three-tier priority

**Tier 1 — Source metadata** (adapter-populated):
- If `item.source_date is not None` → use it directly; skip lower tiers.
- If not set, scan `item.extra_metadata` for known keys in order:
  `["published_at", "date", "publish_date", "created_at", "date_published"]`.
  Parse value as ISO date (`date.fromisoformat(str(v)[:10])`); skip on `ValueError`.
  Use first successful parse.

**Tier 2 — URL date pattern**:
- Only attempted if Tier 1 yielded no date and `item.url` is non-empty.
- Apply stdlib regex:
  ```python
  _URL_DATE_RE = re.compile(r"[/_-](\d{4})[/_-](\d{1,2})[/_-](\d{1,2})(?:[/_\-?#]|$)")
  ```
- Extract `(year, month, day)`. Validate ranges: `1970 ≤ year ≤ 2100`, `1 ≤ month ≤ 12`,
  `1 ≤ day ≤ 31`. Wrap `date(year, month, day)` in `try/except ValueError`; skip on
  invalid calendar date (e.g. month=13, day=32).
- Use the **first** match found.

**Tier 3 — file_mtime**:
- Only attempted if Tiers 1–2 yielded no date.
- If `item.file_mtime is not None` → `item.file_mtime.date()`.

**Fallback**:
- `resolved_date = None`; `review_after` base = `date.today()`.
- Log `WARNING`: `"s3_dates: no date resolved for raw_id=%s"`.

### 2. review_after computation

No `dateutil` (not in `pyproject.toml`). Use `calendar.monthrange` for month arithmetic:

```python
import calendar

_REVIEW_MONTHS: dict[ContentAge, int] = {
    ContentAge.TIME_SENSITIVE: 3,
    ContentAge.DATED:          12,
    ContentAge.EVERGREEN:      36,
    ContentAge.PERSONAL:       6,
}

def _add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year  = d.year + month // 12
    month = month % 12 + 1
    day   = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)
```

Base date:
- `resolved_date` if not None, else `date.today()`.

```python
offset_months = _REVIEW_MONTHS[classification.content_age]
review_after  = _add_months(base_date, offset_months)
```

### 3. Output construction

`NormalizedItem` is a Pydantic v2 model — never mutate in place. Use `model_copy`:

```python
updated_meta = {**item.extra_metadata, "review_after": review_after.isoformat()}
return item.model_copy(update={
    "source_date":    resolved_date,
    "extra_metadata": updated_meta,
})
```

All other fields (`raw_id`, `raw_text`, `title`, `url`, `raw_file_path`, etc.) are
propagated unchanged.

### 4. Logging

```
INFO:  "s3_dates: raw_id=%s source_date=%s review_after=%s date_source=%s"
       (date_source: one of "metadata_field", "url_pattern", "file_mtime", "none")
DEBUG: URL regex match groups (year, month, day) when Tier 2 fires.
DEBUG: extra_metadata keys scanned in Tier 1.
```

Do NOT log `item.url` or `item.raw_text` at INFO or higher (may contain PII).

### 5. Module-level restrictions

- `ObsidianVault` is **not imported or used** — no vault writes whatsoever.
- No `agent.llm.*` imports — no LLM calls.
- No `dateutil`, `dateparser`, or any package not already in `pyproject.toml`.
- Stateless: no module-level mutable state.

---

## Data model changes

None. `NormalizedItem` already has `source_date: date | None = None` and
`extra_metadata: dict[str, Any]`. `review_after` is stored as an ISO string in
`extra_metadata["review_after"]` — no new Pydantic models needed.

---

## LLM prompt file needed

None.

---

## Tests required

### unit: `tests/unit/test_s3_dates.py`

All tests are `async def` (pytest-anyio, `asyncio_mode = "auto"`).
Construct `NormalizedItem` and `ClassificationResult` directly — no mocks needed.

| Case | Description |
|---|---|
| `test_source_date_from_existing_field` | `item.source_date` already set → returned unchanged; tier 2/3 not reached |
| `test_source_date_from_extra_metadata_published_at` | `extra_metadata={"published_at": "2024-01-15"}` → `source_date = date(2024,1,15)` |
| `test_source_date_from_extra_metadata_date_key` | `extra_metadata={"date": "2023-06-01"}` → resolved |
| `test_source_date_from_extra_metadata_key_priority` | Multiple keys present → earliest key in priority list wins |
| `test_source_date_from_url_slash_pattern` | `url = "https://blog.com/2023/07/12/title"` → `source_date = date(2023,7,12)` |
| `test_source_date_from_url_dash_pattern` | `url = "https://example.com/2022-11-03-article"` → `source_date = date(2022,11,3)` |
| `test_url_pattern_skipped_when_tier1_found` | Tier 1 metadata hit → URL not scanned |
| `test_source_date_from_file_mtime` | Tiers 1–2 fail; `file_mtime = datetime(2023,9,5,10,0)` → `source_date = date(2023,9,5)` |
| `test_no_date_resolved_yields_none` | No source_date, empty extra_metadata, empty url, no mtime → `source_date is None` |
| `test_review_after_time_sensitive` | `content_age=TIME_SENSITIVE`, `source_date=date(2024,1,1)` → `review_after = date(2024,4,1)` |
| `test_review_after_dated` | `content_age=DATED`, `source_date=date(2024,1,1)` → `review_after = date(2025,1,1)` |
| `test_review_after_evergreen` | `content_age=EVERGREEN`, `source_date=date(2024,1,1)` → `review_after = date(2027,1,1)` |
| `test_review_after_personal` | `content_age=PERSONAL`, `source_date=date(2024,1,1)` → `review_after = date(2024,7,1)` |
| `test_review_after_uses_today_when_no_date` | `source_date=None` → `review_after` computed from `date.today()` (assert >= today) |
| `test_review_after_in_extra_metadata_as_iso_string` | `result.extra_metadata["review_after"]` is a valid ISO date string |
| `test_original_item_not_mutated` | Input `item.source_date` unchanged after call; result is a different object |
| `test_existing_extra_metadata_preserved` | Other keys in `extra_metadata` survive into result |
| `test_url_invalid_date_skipped` | URL contains `2024/13/45` → skipped; falls to Tier 3 |
| `test_url_year_out_of_range_skipped` | URL contains `/1800/01/01/` → year < 1970; skipped |
| `test_add_months_month_wrap` | `_add_months(date(2024,10,15), 3)` → `date(2025,1,15)` |
| `test_add_months_end_of_month_clamped` | `_add_months(date(2024,1,31), 1)` → `date(2024,2,29)` (2024 is leap) |
| `test_add_months_non_leap_feb` | `_add_months(date(2023,1,31), 1)` → `date(2023,2,28)` |

### integration: `tests/integration/test_pipeline_s3.py` _(low priority)_

- Build a minimal `NormalizedItem` + `ClassificationResult` (no real vault or LLM).
- Call `await s3_dates.run(item, classification)`.
- Assert `result.source_date` is set and `result.extra_metadata["review_after"]` is a valid ISO date string.

---

## Explicitly out of scope

- LLM date inference — no LLM in this stage
- Writing to `_AI_META/processing-log.md` — vault writes are forbidden; use Python `logging` instead
- Timezone-aware datetime handling — all output is naive `date` / ISO strings
- `dateutil`, `dateparser`, or any third-party date library not in `pyproject.toml`
- Parsing non-ISO formats from `extra_metadata` (only `YYYY-MM-DD` or ISO 8601 accepted)
- Phase 2 fields

---

## Open questions

None. All design decisions resolved from feature spec, architecture §5/§6,
REQUIREMENTS §3.1/§6.1, `NormalizedItem` model, and `s2_classify.py` interface contract.
