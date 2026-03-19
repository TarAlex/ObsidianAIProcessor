---
name: verbatim-contract
description: >
  Load this when implementing or testing anything that touches
  agent/vault/verbatim.py or agent/stages/s4b_verbatim.py.
---

## The one rule
VerbatimBlock.content must be byte-identical from extraction through to the final note.
The agent must never paraphrase, strip, or reformat it.

## Render format written to note body
```
<!-- verbatim: type=code lang=python staleness_risk=high
     added_at=2026-03-17 source_id=raw_001 attribution= timestamp= model_target= -->
[raw content here, untouched]
<!-- /verbatim -->
```

## Staleness defaults by type (from ARCHITECTURE.md Appendix A)
| Type       | staleness_risk | extra fields           |
|------------|----------------|------------------------|
| code       | high           | lang                   |
| prompt     | high           | model_target           |
| quote      | low            | attribution            |
| transcript | medium         | timestamp              |

## Max blocks per note
10. If more detected, discard lowest-signal and log the count.

## Test contract (must pass before any verbatim PR)
```python
block = VerbatimBlock(type=VerbatimType.CODE, content="x = 1\n", lang="python",
                      staleness_risk=StatenessRisk.HIGH, added_at=datetime.now())
rendered = render_verbatim_block(block)
parsed   = parse_verbatim_blocks(rendered)
assert parsed[0].content == block.content   # byte-identical
```
