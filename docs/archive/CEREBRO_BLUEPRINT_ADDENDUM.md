# CEREBRO Blueprint Addendum (Experience Systems)

This addendum formalizes the major UI/UX refactor for the CEREBRO Noir direction.
It is intentionally implementation-oriented and phase-scoped.

## Product Structure (authoritative)

Primary studios:
- Mission Control (orientation and launch)
- Live Scan Studio (live operations)
- Decision Studio (flagship duplicate decisions)

Secondary support:
- History
- Diagnostics
- Settings

Budget emphasis:
- Decision Studio: 40%
- Shell: 20%
- Live Scan Studio: 20%
- Mission Control: 10%
- History + Diagnostics + Settings: 10%

## Experience Systems Layer

### 1) Zero-State Philosophy (mandatory)
- Mission first launch: welcome + immediate Start Scan path.
- Scan no-active/interrupted/failed: continuity states, not empty panels.
- Decision no-results/no-duplicates/no-selection: informative safe states.

### 2) Session as first-class UX object
- Session state model is explicit (Idle/Scanning/Paused/Reviewing/Executing/Complete/Interrupted/Failed).
- Shell surfaces compact session presence.
- Mission/Scan/Decision bind to active or resumable session continuity.

### 3) Compare as decision accelerator
- Tier 1: quick peek.
- Tier 2: dedicated compare flow with direct keep actions.
- Tier 3: multi-compare (deferred).

### 4) Predictive Safety Rail
- Risk anticipation (high-confidence, evidence-based only).
- Next-action suggestions.
- Undo-aware trust messaging.

### 5) Activity Feed hierarchy
- Zone 1: critical events.
- Zone 2: progress events.
- Zone 3: detailed log (collapsed by default).

### 6) Keyboard-first command layer
- Global navigation shortcuts.
- Review workflow shortcuts for navigator/workspace/safety actions.
- Shortcut discoverability via cheat sheet.

### 7) Accessibility commitments
- Focus visibility, contrast discipline, full core keyboard flow.
- Plain-language destructive confirmations.
- Respect reduced motion when implemented.

## Implementation Order (approved)

R1 (flagship review core), R1.5 (review intelligence), S1 (shell), S2 (scan),
M1 (mission), X1 (shared systems), then deferred tier-3 and optional features.

## Guardrails

- Context Rail is supplemental only and remains on probation.
- No duplicate dashboards; information should live at the point of action.
- Avoid feature bloat before flagship workflow quality is stable.
