"""rogueworks tooling: art pipeline, content validation, self-test, QA drivers.

Run everything with the project venv (the ``.exe`` launcher is blocked by device
policy on this machine)::

    cd <project root>
    .venv/Scripts/python.exe -m tools.validate_data
    .venv/Scripts/python.exe -m tools.selftest
    .venv/Scripts/python.exe -m tools.art.pixelize --help
    .venv/Scripts/python.exe -m tools.art.pack_atlas --name player_tiles
    .venv/Scripts/python.exe -m tools.art.verify
    .venv/Scripts/python.exe -m tools.art.placeholders
    .venv/Scripts/python.exe -m tools.qa.shot --seed 1 --frames 10,60 --out runs/shots
    .venv/Scripts/python.exe -m tools.qa.scripted_run --seed 1

House rules, shared by every tool:

* **never traceback.** Bad input becomes one clear ``ERROR:`` line on stderr plus a
  documented exit code. Set ``TOOLS_DEBUG=1`` to get the real traceback back.
* **self-create output directories.**
* **empty input is not an error.** A tool with nothing to do prints
  ``0 ... found`` and exits 0, so this repo's tools work on a nearly-empty tree.
* exit 1 means "checked something and it failed"; exit 2 means "prerequisite
  missing / bad usage" (e.g. the game package is not built yet).
"""

__all__ = ["_util"]
