# octk tool bench report

Generated 2026-10-26T11:41:39+00:00. All sizes are characters (approx tokens uses the chars/4 proxy). Retention < 1.0 means a required signal was lost in the pruned output.

## Cases

| case | kind | raw chars | pruned chars | saved % | retention | skipped |
|---|---|---|---|---|---|---|
| pantry_glance | counterfactual | 81507 | 725 | 99.1% | 1.00 | - |
| debug_pruning | measured | 1856 | 734 | 60.5% | 1.00 | - |
| browser_pruning | measured | 65303 | 298 | 99.5% | 1.00 | - |

## Signal detail

- **pantry_glance** (kind=counterfactual): 5/5 signals kept; missed: (none). estimate; raw = bytes of files a full load would have brought, pruned = real glance output
- **debug_pruning** (kind=measured): 3/3 signals kept; missed: (none). real run; raw = unpruned bytes captured, pruned = what octk returned
- **browser_pruning** (kind=measured): 3/3 signals kept; missed: (none). real run; raw = unpruned bytes captured, pruned = what octk returned

## Schema overhead (what the octk MCP server adds to the tool list)

8 tools: names 110 B, descriptions 529 B, JSON schemas 1176 B = 1815 B total (approx 454 tokens).
AGENTS.md root injection: 784 B (approx 196 tokens).

## Honesty

- Savings are measured on this machine, on generated fixtures, at this date; 
  they are not a distribution claim. Retention is scored, never assumed.
- The raw side of kind=counterfactual is an estimate, not a measured run.
- Skipped cases are listed, not silently dropped.
