# UI Consistency and Interaction Audit (Phase 2A)

Audit scope: **Mission**, **Scan**, **Review**, **TopBar**, **NavRail**, **StatusStrip**, **SafetyPanel** (and shared components they use). Purpose: answer the board’s questions and list concrete inconsistencies for a design-system rollout pass.

**Status (2026-03):** History, Diagnostics, and Settings **page headers** use `font_tuple("page_title")` / `page_subtitle` like Mission/Scan/Review. Remaining gaps below (SectionCard, Review workspace gallery fonts, etc.) are **backlog**, not blockers.

---

## Phase 6 triage (feature evaluation)

| Area | Decision |
|------|----------|
| **Simple `ui_mode`** | Dense flows (Export, full Diagnostics, Compare, compact Mission/Scan) are **Advanced-only** or hidden — see `docs/MODE_TOGGLE.md`. |
| **Typography sweep** | **Deferred:** SectionCard, MetricCard, FilterBar, gallery/compare labels in `review_workspace.py`, etc. — track here for a future consistency PR. |
| **Decision-state badges in Group Navigator** | **Deferred:** Review chips/filters exist; per-row badges remain a Phase 2C–style enhancement. |
| **Empty / loading / degraded spec** | **Deferred:** `DegradedBanner` / `EmptyState` in use; full spec doc optional. |
| **Telemetry / pruning** | **N/A** in-app; product backlog only. |

---

## 1. Board questions — answers

### Is the typography hierarchy consistent?

**Partially.**  
- **Consistent:** Mission, Scan, Review use `font_tuple("page_title")` and `font_tuple("page_subtitle")` for headers; SafetyPanel, Scan panels use `font_tuple("data_label")` / `font_tuple("data_value")`; TopBar uses `font_tuple("section_title")`, `font_tuple("caption")`, `font_tuple("strip")`, `font_tuple("body")`; NavRail and StatusStrip use design-system fonts.  
- **Inconsistent:** SectionCard uses `("Segoe UI", 9, "bold")` and `("Segoe UI", 8)` for title/badge. MetricCard, FilterBar, ProvenanceRibbon, StatusRibbon, InsightDrawer, Badge/StatusBadge, EmptyState, review_workspace, and ReviewPage group-detail rows use hardcoded fonts. **History / Diagnostics / Settings page titles** now use `font_tuple` like Mission/Scan/Review. So: **shell + all page headers are on the design system; many cards and gallery/compare labels are not.**

### Are action priorities visually obvious?

**Mostly.**  
- Mission: hero has Accent (Start New Scan) and Ghost (Resume, Open Last Review); Quick Start has Accent + Ghost. Clear.  
- Scan: Cancel is Ghost; primary action is starting scan from Mission. Clear.  
- Review: SafetyPanel uses Danger for “Execute deletion” and Ghost for “Preview effects”; Table/Gallery/Compare mode toggle is neutral. Clear.  
- **Gaps:** No explicit “primary vs secondary” style guide doc; some pages (History, Settings, Diagnostics) use TButton/Accent without a consistent hierarchy. Button hierarchy audit (see below) will standardize.

### Are primary vs secondary pages clearly ranked?

**Yes.**  
- NavRail splits **primary** (Mission, Scan, Review) and **secondary** (History, Diagnostics, Settings) with a separator.  
- Shell and plan match. No change needed for ranking; consistency pass can reinforce (e.g. optional secondary label style).

### Do decision states appear everywhere they should?

**Partially.**  
- **Implemented:** Decision-state model and `DecisionStateBadge` exist; SafetyPanel uses safety rail language (Preview / Execute).  
- **Missing:** Group Navigator rows do not yet show per-group decision-state badges (unresolved / keep selected / ready / warning / skipped). Review workspace shows “Keep this” but not a global decision-state badge per group. Filter/sort by decision state is not implemented. So: **terminology and safety rail are in place; decision-state rollout across Group Navigator and filters is the next step.**

### Are loading / degraded / error states designed, not improvised?

**Mixed.**  
- **Designed:** StatusStrip shows intent lifecycle and engine health; scan ribbon shows scanning/completed/failed; SafetyPanel shows risk flags and reclaimable.  
- **Improvised or missing:** No shared “loading” or “degraded” component; empty states use EmptyState but copy and visuals vary; error feedback is often messagebox or inline text without a consistent pattern. **Recommendation:** define empty/loading/error/degraded state specs and a small set of components (e.g. InlineNotice, DegradedBanner) and then roll them out.

---

## 2. Component-level consistency (design system rollout)

### Page headers

| Page            | Title font              | Subtitle / supporting     | Status        |
|-----------------|-------------------------|---------------------------|---------------|
| Mission         | `font_tuple("page_title")` | `font_tuple("page_subtitle")` | OK            |
| Scan            | `font_tuple("page_title")` | `font_tuple("page_subtitle")` | OK            |
| Review          | `font_tuple("page_title")` | `font_tuple("page_subtitle")` | OK            |
| History         | `font_tuple("page_title")` | `font_tuple("page_subtitle")` | OK (aligned)  |
| Diagnostics     | `font_tuple("page_title")` | `font_tuple("page_subtitle")` | OK (aligned)  |
| Settings        | `font_tuple("page_title")` | `font_tuple("page_subtitle")` | OK (aligned)  |

**Follow-up:** SectionCard and secondary components still mix hardcoded sizes — see Phase 6 triage table above.

### Card titles

| Component   | Current                     | Target                     |
|------------|-----------------------------|----------------------------|
| SectionCard| `("Segoe UI", 9, "bold")`, `("Segoe UI", 8)` | `font_tuple("card_title")`, `font_tuple("data_label")` or `caption` for badge |

**Action:** SectionCard is used by Mission, Scan, Review, History, Diagnostics; standardize on design-system tokens and SPACING for padding.

### Badges / chips

| Component     | Current                | Target                          |
|---------------|------------------------|---------------------------------|
| Badge         | `("Segoe UI", 8, "bold")` | `font_tuple("data_value")` or `caption` |
| StatusBadge   | `("Segoe UI", 8, "bold")` | Same                            |
| TopBar chips  | design_system           | OK                              |
| NavRail       | design_system           | OK                              |

**Action:** Badges.py and any ad-hoc chips should use `font_tuple("caption")` or `font_tuple("data_value")` and SPACING.

### Action button hierarchies

- **Primary (accent):** Accent.TButton — Start New Scan, Start Scan, Execute deletion (destructive uses Danger.TButton).  
- **Secondary:** Ghost.TButton — Resume, Open Last Review, Preview effects, Cancel.  
- **Action:** Document in a short “Button hierarchy” section (e.g. in design_system or README): primary = one per context; secondary = alternative actions; danger = destructive only. Then audit all pages so no page uses TButton where Accent/Ghost/Danger is intended.

### Table / list spacing

- DataTable, Treeview: theme_manager sets rowheight=28 and font.  
- Review group list, History table, Mission recent sessions: spacing is padx/pady in code; not yet using SPACING tokens everywhere.  
**Action:** Use SPACING for list/table padding and gaps in Mission, Scan, Review, History, Diagnostics.

### Status colors

- Success / warning / danger come from theme tokens; StatusStrip, StatusRibbon, SafetyPanel use them.  
- **Action:** Ensure all status indicators (engine health, intent, risk flags, warnings) use theme tokens only; no hardcoded hex.

### Secondary labels

- **Consistent:** SafetyPanel, Scan panels use `data_label` / `data_value`.  
- **Inconsistent:** Diagnostics, History, FilterBar, ProvenanceRibbon, SectionCard badge use hardcoded 8pt.  
**Action:** Replace with `font_tuple("data_label")` or `font_tuple("caption")` and, where appropriate, `font_tuple("data_value")`.

---

## 3. Interaction depth (next layer)

- **Shortcut flows / batch actions:** Not implemented; document as Phase 2A/2C.  
- **Empty/error/degraded states:** No shared spec; EmptyState exists but is not standardized. Recommend: one doc (e.g. `EMPTY_ERROR_DEGRADED_SPEC.md`) and optional shared components.  
- **Scan → Review handoff:** App navigates and loads result on terminal; StatusStrip shows intent. Could add a short “Scan complete — go to Review” cue on Scan page when terminal fires.  
- **“What should I do next?”:** Mission hero is clear; Review could add a small hint when no keep is selected (e.g. “Choose a file to keep in each group”).

---

## 4. Summary and recommended order

1. **Typography consistency pass:** History, Diagnostics, Settings page headers; SectionCard; MetricCard; FilterBar; ProvenanceRibbon; StatusRibbon; InsightDrawer; Badge/StatusBadge; ReviewPage group detail; EmptyState. Use `font_tuple` and SPACING.  
2. **Button hierarchy:** Document primary/secondary/danger and audit all pages.  
3. **Decision-state rollout:** Add decision-state badges to Group Navigator rows; add filter/sort by decision state (Phase 2C).  
4. **Empty/loading/error/degraded:** Write short spec and add/reuse components where needed.  
5. **Scan→Review and “what next”:** Small UX tweaks after the above.

This audit should be the single reference for the “consistency sweep” and “component standardization” called out in the rebased plan.
