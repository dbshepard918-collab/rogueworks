"""QA drivers: run the game through its documented CLI and collect evidence.

* ``shot``         - render specific simulation ticks to PNGs (headless)
* ``scripted_run`` - replay a scripted-input JSON and audit the run summary

Both drive the game **only** through ``python -m game.main`` (docs/CONTRACTS.md
section 3) via subprocess, so they keep working while the game is still being
written and never poke at game internals.

    python -m tools.qa.shot --seed 1 --frames 10,60 --out runs/shots
    python -m tools.qa.scripted_run --seed 1 --turns 300
"""

__all__ = ["shot", "scripted_run", "regression"]
