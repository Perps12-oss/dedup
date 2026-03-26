# UI architecture (desktop shells)

High-level data flow for **CEREBRO** ttk (`CerebroApp`) and CustomTkinter (`CerebroCTKApp`) shells. Both share the same orchestration contracts: one `ScanCoordinator`, `ApplicationRuntime` facades, `ProjectionHub`, and `UIStateStore`.

```mermaid
flowchart TB
  subgraph UI["UI shells"]
    TTK["CerebroApp / AppShell"]
    CTK["CerebroCTKApp"]
  end

  subgraph Facades["ApplicationRuntime"]
    SCAN["ScanApplicationService"]
    HIST["HistoryApplicationService"]
    REV["ReviewApplicationService"]
  end

  subgraph Orch["Orchestration"]
    COORD["ScanCoordinator"]
    BUS["EventBus"]
  end

  subgraph Proj["Projections"]
    HUB["ProjectionHub"]
    ADAPTER["ProjectionHubStoreAdapter"]
  end

  subgraph State["UI state"]
    STORE["UIStateStore"]
  end

  subgraph Engine["Engine"]
    PIPE["Pipeline / scan workers"]
    DEL["deletion / models"]
  end

  TTK --> SCAN
  TTK --> HIST
  TTK --> REV
  CTK --> SCAN
  CTK --> REV
  CTK --> HIST

  SCAN --> COORD
  HIST --> COORD
  REV --> COORD
  COORD --> BUS
  COORD --> PIPE
  COORD --> DEL

  BUS --> HUB
  HUB --> ADAPTER
  ADAPTER --> STORE
  TTK --> STORE
  CTK --> STORE
```

**Contracts**

- **Hub:** Delivers frozen projection snapshots on the Tk main thread; UI widgets must not subscribe to the raw `EventBus`.
- **Store:** Canonical cross-page state (`scan`, `review`, `mission`, `history`, `ui_mode`, `ui_degraded`).
- **Controllers:** `ScanController` / `ReviewController` call services (not pages) for start/cancel/delete intents.

For boundary detail, see [BOUNDARY_AUDIT.md](BOUNDARY_AUDIT.md).
