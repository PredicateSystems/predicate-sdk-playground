# WebVoyager Demo Plan (Sentience SDK Playground)

This document captures potential challenges when running WebVoyager-style tasks with
compact prompts, and the mitigations available in the Sentience SDK.

---

## Potential Challenges and Mitigations

1) **Static text dependencies** (labels, headings, confirmations)
   - **Challenge**: compact prompts may miss critical non-interactive text.
   - **Mitigation**: use `read(format="text"|"markdown")` on demand; leverage `nearby_text`
     surfaced for top-ranked elements.

2) **Icon-only or canvas-heavy UIs**
   - **Challenge**: no reliable text/role cues for element IDs.
   - **Mitigation**: `find_text_rect` + `click_rect` for coordinate actions; vision fallback.

3) **Dynamic DOM / re-rendering**
   - **Challenge**: element IDs change between steps.
   - **Mitigation**: use assertions + `eventually()`; re-snapshot between actions.

4) **Ambiguous element selection**
   - **Challenge**: multiple similar buttons/links.
   - **Mitigation**: ordinal hints (`first`, `second`, `top`); dominant group metadata.

5) **Hidden/disabled state changes**
   - **Challenge**: element appears but is disabled or hidden by overlays.
   - **Mitigation**: `is_enabled`, `exists`, `verify_text_present`; wait for state.

6) **Navigation timing (SPA transitions)**
   - **Challenge**: URL updates are delayed or async.
   - **Mitigation**: `assert_eventually_url_matches`, `eventually(url_contains(...))`.

7) **Token usage explosion from `read()`**
   - **Challenge**: reading full pages can bloat context.
   - **Mitigation**: use `format="text"`; clip length; only call when needed.

8) **Role inference gaps**
   - **Challenge**: inputs/buttons without labels or placeholders.
   - **Mitigation**: inferred labels from the extension; `nearby_text` hints.

9) **Cross‑origin iframes**
   - **Challenge**: elements inside iframes can be missed.
   - **Mitigation**: the sentience‑chrome extension collects iframe snapshots and flattens
     them into the main element list when injection is allowed. Caveats: some frames may
     block injection or be sandboxed, so use `read()`/vision fallback if content is missing.

10) **Visual disambiguation (layout‑based cues)**
   - **Challenge**: “the button on the right” isn’t captured in text.
   - **Mitigation**: use `bbox`, `center_x/center_y`, and ordinal grouping.

---

## Planned WebVoyager Test Tasks (Demo List)

These are **planned** tasks for the compact‑prompt evaluation. Adjust based on the
WebVoyager subset you choose to run.

1. **Search + click result**
   - Example: Search a site and open the first result.

2. **Login flow**
   - Enter credentials, verify enabled state, submit.

3. **Form completion**
   - Fill multi‑field form with validation, submit, verify success text.

4. **Product discovery**
   - Search, open product, add to cart, verify cart count.

5. **Navigation + settings change**
   - Navigate to settings/profile, toggle a preference, verify state.

6. **Table extraction**
   - Read a table/list and return a specific row’s value.

7. **Filter + sort**
   - Apply filters/sort, confirm top result matches expected criteria.

8. **Download or export**
   - Trigger export/download, confirm notification text.

9. **Map or location search**
   - Search location and confirm address details.

10. **Dashboard KPI extraction**
   - Read KPIs and verify presence of named metrics.

---

## Metrics to Track

- Success rate
- Token usage (total + per step)
- Latency per task
- Retry count
- Vision fallback rate

---

## Notes

- Use compact prompts by default, with `read()` only on ambiguity.
- Log any failures with screenshots + snapshot for post‑mortem analysis.
