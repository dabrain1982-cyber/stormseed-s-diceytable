#!/usr/bin/env python3
"""Place the generated base game as physical objects in setup.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ZERO = {"x": 0, "y": 0, "z": 0}


def state(object_id, kind, label, position, **values):
    result = {
        "id": object_id,
        "kind": kind,
        "label": label,
        "displayName": values.pop("displayName", label),
        "position": position,
        "rotation": values.pop("rotation", ZERO),
        "scale": values.pop("scale", {"x": 1, "y": 1, "z": 1}),
        "color": values.pop("color", "#ffffff"),
        "ownerSeat": None,
        "faceDown": values.pop("faceDown", False),
        "locked": values.pop("locked", False),
        "stackCount": values.pop("stackCount", 1),
        "tags": values.pop("tags", ["stormseed-conquest"]),
        "metadata": values.pop("metadata", {}),
        "velocity": ZERO,
        "angularVelocity": ZERO,
    }
    result.update(values)
    return result


def deck_state(root: Path, slug: str, object_id: str, label: str, x: float, z: float):
    definition = json.loads((root / f"assets/decks/{slug}.deck.json").read_text())
    return state(
        object_id,
        "deck",
        object_id,
        {"x": x, "y": 2.19, "z": z},
        displayName=label,
        color="#f6f1df",
        faceDown=True,
        stackCount=sum(card.get("count", 1) for card in definition["cards"]),
        material="card",
        containerMode="stack",
        metadata={"customDeck": definition, "paperThicknessMm": 0.3},
    )


def die_state(number: int, color: str, x: float, z: float, role: str):
    return state(
        f"stormseed-d6-{role}-{number}",
        "die",
        f"d6-{role}-{number}",
        {"x": x, "y": 2.2, "z": z},
        displayName=f"{role.capitalize()}swürfel {number}",
        scale={"x": 0.16, "y": 0.16, "z": 0.16},
        color=color,
        material="plastic",
        tags=["stormseed-conquest", f"{role}-dice"],
        metadata={
            "standardPresetId": "die-d6",
            "standardPresetFamily": "dice",
            "standardPresetVariant": "d6",
            "dieSides": 6,
            "dieFaceStyle": "dots",
        },
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=Path(__file__).resolve().parents[1], type=Path)
    parser.add_argument("--style", choices=("klassisch", "taktisch", "farbenfroh"), default="klassisch")
    args = parser.parse_args()
    root = args.root.resolve()
    setup_path = root / "setup.json"
    setup = json.loads(setup_path.read_text())
    setup["objects"] = [
        obj for obj in setup.get("objects", [])
        if not str(obj.get("id", "")).startswith("stormseed-")
    ]

    style = args.style
    pieces = [
        state(
            "stormseed-world-board",
            "board",
            "stormseed-world-board",
            {"x": 0, "y": 2.095, "z": 0},
            displayName=f"Weltbrett – {style.capitalize()}",
            scale={"x": 4.35, "y": 0.04, "z": 2.72},
            color="#ffffff",
            locked=True,
            material="wood",
            metadata={"boardImageUrl": f"assets/boards/welt-{style}.webp"},
        ),
        deck_state(root, f"laender-{style}", "stormseed-country-deck", "42 Länderkarten", 2.48, 0.82),
        deck_state(root, f"missionen-{style}", "stormseed-mission-deck", "12 Missionskarten", 2.48, 1.35),
        die_state(1, "#c43d3d", -2.55, -0.62, "angriff"),
        die_state(2, "#c43d3d", -2.35, -0.62, "angriff"),
        die_state(3, "#c43d3d", -2.15, -0.62, "angriff"),
        die_state(1, "#26313d", -2.45, -1.02, "verteidigung"),
        die_state(2, "#26313d", -2.25, -1.02, "verteidigung"),
    ]
    setup["objects"].extend(pieces)
    setup_path.write_text(json.dumps(setup, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
