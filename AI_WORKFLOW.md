# Working with AI on this

I used AI coding assistants throughout, as the challenge asks. The detailed record is
[DECISIONS.md](DECISIONS.md), where every entry is marked `decided` (my call) or `ai-default` (accepted as
proposed), with the alternatives that were considered. This page pulls together, from that log:
- where I overrode a proposal;
- which defaults I kept;
- what checking the running system caught;
- what changed after a practice panel review of the finished code.

## Where I overrode a proposal

| Proposed | What was done | What the log records |
|---|---|---|
| Industry as a foreign key on Brand | Many-to-many | "My choice, over the recommended ForeignKey, faithful to WP's non-hierarchical taxonomy" (D1) |
| A hand-rolled fetch hook for `<BrandList />` | TanStack Query | "My choice, over the recommended hand-rolled hook": caching, dedup, cancellation, `keepPreviousData`, at the cost of a dependency I must be able to explain (D5) |
| Expand/contract for breaking token changes | A `v` claim with per-version encode/decode | Auth can issue several versions at once, so each consumer moves on its own schedule (D8d) |
| An abstract `WPSourced` base model | Fields declared on each model | Removed at my request (D3 notes) |
| A `short_description` field on Brand | Removed; cards show an excerpt of `description` | WordPress has one body per brand and an empty excerpt, so the first build had invented a second field (D1) |
| Parsing `dump.sql` (the parser was built and matched the database) | Read the WordPress MariaDB directly | I preferred the database route (D3) |

## Defaults I kept

Recorded as `ai-default` in `DECISIONS.md`:
- **Platform:** the monorepo with one uv workspace and a Postgres per service; Django 5.2 with DRF; the frontend toolchain.
- **Auth:** Ed25519 signing keys stored in the database; the 10-minute and 7-day token lifetimes; refresh rotation without reuse detection; the `JWKSClient` timings; the 503 rule for introspection; the `testing` module living in the library.
- **Frontend:** skeleton loading states; `aria-busy` dimming; focus to results on paging.
- **SCSS:** the token functions that error on typos; the desktop-first breakpoint.
- **Data:** nh3 and its allowlist; PyMySQL.

## What checking the running system caught

From the "Review pass" section of the log. Each item has a regression test.
- `?industry=%00` crashed the public listing, because Postgres rejects NUL bytes.
- `PATCH` validation crashed on a JSON array or a bare number.
- The API accepted form-encoded bodies.
- `X-Frame-Options` was missing.
- The two admins shared session cookies on `localhost`.
- Annotating a queryset dropped its default ordering.
- axe's "incomplete" results had been read as passes. Contrast was then computed by hand.

## Changes after a practice panel review

Before submitting, I had the finished repo reviewed as the panel would review it. The tag `review-baseline` marks
the code before that review, and `git diff review-baseline..main` shows every change since. Each commit quotes the
review finding it answers.

| Commit | What changed | Review finding |
|---|---|---|
| `app: remove the Django admin` | The main app's admin and its sign-in through the auth service | Out of scope, and its sign-in kept a staff flag per editor in the main app, a cached role |
| `app: remove static pages and the reviews archive` | `/<slug>/` pages, `/review/`, `/review/page/<n>/` | "They weren't asked for" |
| `api: only authenticate PATCH on the brand detail endpoint` | A public GET ignores the `Authorization` header | A public GET could return 401 or 503 |
| `frontend: native <select> for sorting` | The custom ARIA listbox was replaced | It departed from the WAI-ARIA listbox pattern |
| `scss: font-weight tokens; make the token rule accurate` | Weight tokens, and an accurate header comment | The comment said components never write raw values; 14 rules did |
| `auth: purge expired refresh tokens and retired signing keys` | `purge_tokens` and an index on `expires_at` | Refresh tokens and retired keys were never deleted |
| `docs: …` | API contract and "top review" definition in the README, the SCSS compile command, this page | The brief asks for both; they were only in code comments |

Also changed during that review: WordPress's stored `average_rating` is no longer imported. It is only documented
that it disagrees with the reviews for 4 of 5 brands. This change is folded into the original model and import
commits.

## About this git history

The work was first committed as a series of save points. Before submitting, it was regrouped:
- **Up to `review-baseline`:** the code committed area by area so it reads in order. These commits were regrouped
  after the fact and carry the regrouping date. Only the last one is guaranteed to build and pass.
- **After `review-baseline`:** the review changes, one per commit, each tested on its own.

The regrouping and the review changes were made with Claude, so those commits carry a `Co-Authored-By: Claude`
trailer.
