"""Art pipeline (docs/CONTRACTS.md sections 5-6).

raw AI art -> ``pixelize`` (palette lock + 32px grid slice) -> ``pack_atlas``
(sheet + rect manifest) -> ``verify`` (palette / geometry gate).

    assets/raw/*.png  --pixelize-->  assets/sprites/<name>/*.png
                      --pack_atlas-> assets/atlas/<name>.png + <name>.json
                      --verify----->  exit 0 or a list of every off-palette pixel
"""

__all__ = ["pixelize", "pack_atlas", "verify", "placeholders"]
