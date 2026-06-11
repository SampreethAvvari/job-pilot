# Company-size filter — design

**Date:** 2026-06-10
**Status:** implemented on `feat/company-size-filter`

## Goal

Let the user filter the jobs and applied tables by employer size category
(mega corporations down to startups, plus educational institutions), so the
job hunt can be focused on a preferred kind of employer.

## Buckets

Size is bucketed by approximate global headcount; `Educational` overrides
headcount because it is a kind, not a size.

| Bucket        | Meaning                                            |
| ------------- | -------------------------------------------------- |
| `Mega`        | ~100k+ employees (Amazon, Microsoft, JPMorgan, …)  |
| `Big`         | ~10k–100k (Nvidia, Adobe, Uber, Goldman Sachs, …)  |
| `Medium`      | ~1k–10k (Databricks, Stripe, OpenAI, Figma, …)     |
| `Small`       | ~200–1k (Vercel, Notion, Weights & Biases, …)      |
| `Startup`     | under ~200 (Supabase, Linear, Modal, …)            |
| `Educational` | universities, colleges, schools, research institutes |
| `Unknown`     | not classified                                     |

## Approach

**Client-side name classifier, UI only.** A new pure module
`ui/src/lib/company-size.ts` maps the existing `Company` string to a bucket:

1. normalize the name (lowercase, strip punctuation, strip legal suffixes
   like Inc/LLC/Corp/Ltd/Technologies, leading "The");
2. exact lookup in a curated map of well-known employers (weighted toward
   US software-hiring companies, since that is what the pipeline ingests);
3. heuristic pass for educational institutions
   (university / college / school / institute / academy …);
4. otherwise `Unknown`.

No new Sheet column, no pipeline change — the `HEADERS` sync invariant
between `sheets.py` and `ui/src/lib/types.ts` is untouched, and the change
is fully contained in the console UI.

**Alternative considered:** classify during ingestion (Gemini already scores
each job) and persist a `Company size` column in the Sheet. More accurate
for long-tail companies, but cross-cutting (pipeline + Sheet migration +
header sync in two codebases). If name-lookup accuracy turns out to be
insufficient, that becomes the upgrade path and this classifier remains the
fallback for old rows.

## UI

In `jobs-table.tsx` (shared by `/jobs` and `/applied`):

- a new `size:` dropdown beside the existing status/source/role/fit filters,
  options: all + the seven buckets, in size order;
- a faint size tag under the company name when the bucket is known, so the
  filter's behavior is visible and debuggable at a glance;
- filtering happens in the existing `visible` useMemo chain, same pattern as
  the other filters.

## Error handling

Classification cannot fail — any unmatched or empty company name is
`Unknown`, which is itself filterable. Misclassifications are fixed by
editing the curated map.

## Testing

The UI has no JS test runner (lint + `next build` are the repo gates), so
verification is: a one-off node run of the classifier against representative
names, `npm run lint`, and `npm run build`.
