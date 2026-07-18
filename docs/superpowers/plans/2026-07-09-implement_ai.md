# AI-søk: Real AI-powered turnus search

## Context

The site currently has an "AI Generer favoritter" feature (`app/utils/shift_matcher.py` + import-favorites flow) that is labeled AI but is a plain statistical similarity matcher. The goal is to make the AI label honest by adding a genuinely AI-powered way to find turnuses.

**Decisions made with the user (brainstorming):**
- **Scope:** Natural-language search + smarter recommendations, sharing one backend.
- **Architecture: Hybrid.** LLM parses the user's Norwegian free text into structured preferences → existing deterministic stats ranking scores all turnuses → LLM writes short Norwegian justifications for the top ~10. The LLM never ranks; ranking stays deterministic and reproducible.
- **UI:** One «AI-søk» box on the turnusliste page; the existing «Generer favoritter» import flow additionally gets AI justifications on its matches.
- **Model:** Claude Sonnet 5 (`claude-sonnet-5`) via the official `anthropic` Python SDK. ~1–3 øre per search with prompt caching. Local/open-source LLM ruled out (2 vCPU / 4 GB Hetzner VPS).
- **Unmappable wishes:** "Map + be honest" — response explicitly lists which parts of the wish were understood vs. ignored.

**Key discovery:** `app/static/js/modules/sorting-system.js` already implements the exact ranking model to target: a weight vector (−10..+10) per stats column, min-max normalized, weighted sum (`calculateScore`). The AI parser emits that same weight shape → consistent with the existing slider UX.

**Data available:** `turnus_stats_{ID}.json` — 57 turnuses × 26 stat columns (`tidlig`, `ettermiddag`, `natt`, `natt_helg`, `helgetimer`, `helgedager`, `before_6`, `tidlig_6_8`, `tidlig_8_12`, `longest_off_streak`, `longest_work_streak`, `avg_shift_hours`, `mon_off_rate`…`sun_off_rate`, `start_time_std`, etc.), loaded/cached by `DataframeManager` (`app/utils/df_utils.py`). Kompdag counts per linje from `count_kompdager()` (`app/utils/kompdag_utils.py`) can be mentioned in justifications.

## Design

### 1. Config & dependency
- Add `anthropic` to `requirements.txt`.
- `config.py`: `ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY", "")` following the existing `_env` pattern; add to `.env.example` with a comment.
- Feature is **soft-disabled when the key is missing**: the search box is hidden (template conditional on a config flag), API returns a clear Norwegian error. Never crash at import time.

### 2. Service layer — `app/services/ai_search_service.py` (new)
Follows the strict Routes → Services → DB layering. Three functions:

**`parse_preferences(text: str) -> dict`**
- One Sonnet 5 call using **structured outputs** (`output_config.format` per current API; NOT the deprecated `output_format`) so the response is guaranteed-valid JSON.
- System prompt (Norwegian domain glossary: natt, helg, tidligvakt, delt dagsverk, kompdager, langfri…) with `cache_control` breakpoint so repeat searches hit the prompt cache.
- Returns: `{"weights": {stat_col: -10..10}, "hard_constraints": [{"stat": ..., "op": "<=", "value": ...}], "understood": ["fri i helger"], "ignored": ["når barnehagen er stengt"], "off_topic": false}`.
- Only known stat columns allowed in the schema (enum), so the parser can't invent fields.

**`rank_turnuses(parsed: dict, turnus_set_id: int) -> list[dict]`**
- Pure Python/pandas, no LLM. Port of `calculateScore` from `sorting-system.js`: min-max normalize each weighted column, weighted sum, negative weight inverts. Apply hard constraints as filters first (with graceful fallback if they eliminate everything: drop constraints, note it in response).
- Data source: stats DataFrame via existing `DataframeManager` / `shift_matcher.load_stats_for_turnus_set`.

**`explain_matches(user_text, parsed, top_matches: list) -> dict`**
- Second Sonnet 5 call: sends only the top ~10 rows (compact TSV) + user text + parsed summary. Returns per-turnus 1–2 sentence Norwegian justification plus an honest note about ignored wishes. Structured output again.
- Same function is reused by the import-favorites flow (mode flag changes the prompt framing: "why this matches your previous favorites" vs "why this matches your wish").

**Error handling:** catch the SDK's typed exceptions most-specific-first (`RateLimitError` → `APIStatusError` → `APIConnectionError`), return `{"error": <norwegian message>}` — never a stack trace to the user. 30 s timeout on the client.

### 3. API route — `app/routes/api.py`
- `POST /api/ai-search` — `@login_required`. Body: `{"text": ...}`. Validates length (e.g. 3–500 chars).
- **Rate limit:** simple per-user counter in the existing Flask-Caching store (e.g. max 10 searches / 5 min per user) — protects the wallet.
- **Result cache:** key `ai_search_{turnus_set_id}_{sha1(text)}`, ~1 h TTL — repeated identical searches are free.
- Response: `{status, understood, ignored, matches: [{turnus, score, justification, stats_summary, kompdager_max}]}`.
- Extend `POST /api/import-favorites-preview` with an optional `explain: true` flag that runs `explain_matches` over its results (keeps existing behavior unchanged by default).

### 4. Frontend
- **Turnusliste**: an «AI-søk» panel (navbar button with the existing `gen-favorites-ai-label` styling → collapsible input card): textarea with Norwegian placeholder examples, submit button with spinner, result list showing rank, turnus name, justification, kompdag badge, favorite-star toggle (reuse existing favorite JS), and an «forstått / ikke forstått» transparency line.
- **Bonus reuse:** after a search, set the existing sorter sliders to the parsed weights (they share the same scale) so the main list re-sorts to match and the user can fine-tune manually.
- New module `app/static/js/modules/ai-search.js` (class, imported from `main.js`), CSS in `app/static/css/` per-feature file. Norwegian UI text, no inline styles, Bootstrap 5 + `bi-*` icons, purple gradient theme.

### 5. Testing (`tests/test_ai_search_service.py`, `tests/test_ai_search_routes.py`)
- Mock the Anthropic client at the use site (`monkeypatch.setattr("app.services.ai_search_service._get_client", ...)`) — no network in tests.
- Unit-test `rank_turnuses` against a small stats fixture with hand-computed expected ordering (deterministic, so exact asserts).
- Route tests: auth required, rate limiting, missing-API-key behavior, malformed input, happy path with mocked LLM responses.
- Follow existing fixture layers (`patch_db`, `client`, `sample_user`).

## Files to create/modify

| File | Change |
|---|---|
| `requirements.txt` | add `anthropic` |
| `config.py`, `.env.example` | `ANTHROPIC_API_KEY` |
| `app/services/ai_search_service.py` | **new** — parse / rank / explain |
| `app/routes/api.py` | `POST /api/ai-search`; `explain` flag on import-preview |
| `app/templates/turnusliste.html` | AI-søk panel (conditional on key configured) |
| `app/static/js/modules/ai-search.js` | **new** — UI module |
| `app/static/js/main.js` | import new module |
| `app/static/css/turnusliste/ai-search.css` | **new** — panel styling |
| `tests/test_ai_search_service.py`, `tests/test_ai_search_routes.py` | **new** |
| `docs/superpowers/specs/2026-07-09-ai-search-design.md` | design doc (committed at implementation start, per brainstorming skill) |

No DB schema changes → no Alembic migration needed.

## Cost & ops summary
- 2 Sonnet 5 calls per search: parse (~500 in / 200 out tokens) + explain (~2–4k in / 500 out) ≈ **1–3 øre per search** with prompt caching; result cache + rate limit cap worst-case spend.
- Nothing personal is sent to the API: public turnus stats + an anonymous preference sentence.
- If the key is absent (e.g. dev without key), the site works exactly as today.

## Verification
1. `pytest` — all new and existing tests green.
2. Manual end-to-end with a real key in `.env`: run `python run.py`, log in, search e.g. «lite netter, fri annenhver helg, helst sen start» → verify ranked results with Norwegian justifications, honest understood/ignored line, slider sync, favorite toggle works.
3. Search something unmappable («fri når barnehagen er stengt») → verify it appears under "ikke forstått".
4. Remove key from `.env` → verify the panel is hidden and `/api/ai-search` returns the friendly error.
5. Fire 11 searches quickly → verify rate-limit message.
