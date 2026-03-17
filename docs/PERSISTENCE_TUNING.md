# Persistence write-path tuning

Safe defaults are used; override only when you need stricter durability or measured gains.

## Environment knobs (optional)

- **`DEDUP_SQLITE_WAL`** — Set to `0` or `false` to disable WAL mode (default: enabled). WAL improves concurrent read/write; disable only if you hit compatibility issues.
- **`DEDUP_SQLITE_SYNCHRONOUS`** — One of `FULL`, `NORMAL`, `OFF`. Default `NORMAL` balances safety and speed. Use `FULL` for maximum durability (e.g. unreliable storage).

## Pipeline tuning (config)

- **Inventory batch size** — `ScanConfig.batch_size` (and app config batch size where used). Larger batches reduce commit frequency at the cost of memory and resume granularity.
- **Checkpoint cadence** — `ScanConfig.checkpoint_every_files`. How often the pipeline writes resume checkpoints; decoupled from inventory commits.

Defaults remain safe; resume correctness and checkpoint integrity are preserved. Run tests (e.g. `test_resume`, `test_pipeline`, `test_persistence_*`) to verify after changing tuning.
