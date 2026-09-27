"""Structural contracts for the source-order v2 recipe examples.

The v2 fixtures intentionally stay independent of registry loading while the
new acquisition-frontier stage is being integrated by the extension owner.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

RECIPES = Path(__file__).resolve().parents[1] / "tensile_extras" / "recipes"
FRONTIER = "tensile.acquisition_frontier_v1"
PROOF = "tensile.source_proof_stress"
SUPPORT = "tensile.source_support_order_full_v1"


@pytest.mark.parametrize(
    ("profile", "retention"),
    [
        ("uniform", "first measured force peak"),
        ("tail", "post-peak model tail"),
    ],
)
def test_v2_profiles_copy_v1_methods_and_insert_one_frontier_stage(
    profile: str, retention: str
) -> None:
    v1 = json.loads(
        (RECIPES / f"source_order_{profile}_v1_examples.json").read_text(encoding="utf-8")
    )
    v2 = json.loads(
        (RECIPES / f"source_order_{profile}_v2_examples.json").read_text(encoding="utf-8")
    )

    assert v2["schema"] == f"matnexus.tensile.source_order_{profile}_v2_examples/1"
    assert len(v1["recipes"]) == len(v2["recipes"]) == 7
    assert len({recipe["key"] for recipe in v2["recipes"]}) == 7
    assert FRONTIER in v2["description"]
    assert "acquisition frontier" in v2["description"]
    assert retention in v2["description"]
    description = f"{v2['description']} " + " ".join(
        recipe["description"] for recipe in v2["recipes"]
    )
    assert "default" not in description.casefold()
    assert "material-card" not in description.casefold()
    assert "card approval" not in description.casefold()

    for old, new in zip(v1["recipes"], v2["recipes"], strict=True):
        assert new["key"] == old["key"].replace("_v1_", "_v2_", 1)
        assert new["test_type_key"] == old["test_type_key"] == "tensile"
        assert FRONTIER in new["description"]
        assert "acquisition frontier" in new["description"]
        assert retention in new["description"]

        old_steps = old["steps"]
        new_steps = new["steps"]
        assert sum(step["plugin"] == FRONTIER for step in new_steps) == 1
        frontier_index = next(
            index for index, step in enumerate(new_steps) if step["plugin"] == FRONTIER
        )
        assert new_steps[frontier_index]["options"] == {}
        proof_index = next(
            index for index, step in enumerate(new_steps) if step["plugin"] == PROOF
        )
        support_index = next(
            index for index, step in enumerate(new_steps) if step["plugin"] == SUPPORT
        )
        assert proof_index < frontier_index < support_index

        without_frontier = [step for step in new_steps if step["plugin"] != FRONTIER]
        assert without_frontier == old_steps

        old_method = next(
            step
            for step in old_steps
            if step["plugin"] in {"tensile.band_model", "tensile.model_curve"}
        )
        new_method = next(
            step
            for step in new_steps
            if step["plugin"] in {"tensile.band_model", "tensile.model_curve"}
        )
        assert new_method["plugin"] == old_method["plugin"]
        assert new_method["options"] == old_method["options"]
