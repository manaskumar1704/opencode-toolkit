# octk tool bench report

Generated 2026-10-26T18:47:58+00:00. All sizes are characters (approx tokens uses the chars/4 proxy). Retention < 1.0 means a required signal was lost in the pruned output.

## Cases

| case | kind | raw chars | pruned chars | saved % | retention | skipped |
|---|---|---|---|---|---|---|
| pantry_glance | counterfactual | 81622 | 838 | 99.0% | 1.00 | - |
| debug_pruning | measured | 1856 | 734 | 60.5% | 1.00 | - |
| browser_pruning | measured | 65303 | 298 | 99.5% | 1.00 | - |

## Signal detail

- **pantry_glance** (kind=counterfactual): 5/5 signals kept; missed: (none). estimate; raw = bytes of files a full load would have brought, pruned = real glance output
- **debug_pruning** (kind=measured): 3/3 signals kept; missed: (none). real run; raw = unpruned bytes captured, pruned = what octk returned
- **browser_pruning** (kind=measured): 3/3 signals kept; missed: (none). real run; raw = unpruned bytes captured, pruned = what octk returned

## Schema overhead (what the octk MCP server adds to the tool list)

9 tools: names 128 B, descriptions 598 B, JSON schemas 1490 B = 2216 B total (approx 554 tokens).
AGENTS.md root injection: 1034 B (approx 259 tokens).

## Honesty

- Savings are measured on this machine, on generated fixtures, at this date; 
  they are not a distribution claim. Retention is scored, never assumed.
- The raw side of kind=counterfactual is an estimate, not a measured run.
- Skipped cases are listed, not silently dropped.
