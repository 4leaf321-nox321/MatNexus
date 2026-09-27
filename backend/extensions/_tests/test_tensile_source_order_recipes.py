"""The opt-in tensile profiles keep source evidence ahead of model processing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from matcore import extensions, processing, registry

RECIPES = Path(__file__).resolve().parents[1] / "tensile_extras" / "recipes"
BASE = RECIPES / "coordinate_projection_v1_examples.json"
extensions.load(RECIPES.parents[1])
processing.load_builtin()


@pytest.mark.parametrize("profile", ["uniform", "tail"])
def test_seven_method_profiles_preserve_methods_and_source_contract(profile: str) -> None:
    baseline = json.loads(BASE.read_text(encoding="utf-8"))["recipes"]
    candidate = json.loads(
        (RECIPES / f"source_order_{profile}_v1_examples.json").read_text(encoding="utf-8")
    )
    assert candidate["schema"] == f"matnexus.tensile.source_order_{profile}_v1_examples/1"
    assert len(candidate["recipes"]) == len(baseline) == 7
    assert len({recipe["key"] for recipe in candidate["recipes"]}) == 7

    for old, new in zip(baseline, candidate["recipes"], strict=True):
        steps = new["steps"]
        ids = [step["plugin"] for step in steps]
        for plugin_id in ids:
            registry.get(plugin_id)
        assert new["test_type_key"] == old["test_type_key"] == "tensile"
        assert (
            ids.index("tensile.source_peak_evidence_v1")
            < ids.index("tensile.source_elastic_modulus_v2")
            < ids.index("tensile.source_proof_stress")
        )
        assert (
            ids.index("tensile.source_proof_stress")
            < ids.index("tensile.source_stress_snapshot")
            < ids.index("tensile.true_plastic")
        )
        assert (
            ids.index("tensile.plastic_coordinate_order_guard")
            < ids.index("curve.monotone")
            < ids.index("curve.resample")
        )
        assert ids.count("curve.resample") == 1
        assert (
            next(
                step
                for step in steps
                if step["plugin"] == "tensile.plastic_coordinate_order_guard"
            )["options"]["source_index"]
            == "auto"
        )

        proof = next(step for step in steps if step["plugin"] == "tensile.source_proof_stress")
        domain = next(
            step for step in steps if step["plugin"] == "tensile.effective_card_domain"
        )
        if profile == "uniform":
            assert (
                ids.index("tensile.source_proof_stress")
                < ids.index("tensile.source_support_order_full_v1")
                < ids.index("tensile.prepeak_prefix")
            )
            assert ids.index("tensile.prepeak_prefix") < ids.index("tensile.model_support")
            assert proof["options"]["end_index"] == "@source_peak_index"
            assert domain["options"]["policy"] == "uniform_measured_v1"
            assert "tensile.source_terminal_domain_v1" not in ids
            assert "tensile.source_support_order_guard" not in ids
        else:
            assert (
                ids.index("tensile.source_proof_stress")
                < ids.index("tensile.source_support_order_full_v1")
                < ids.index("tensile.source_terminal_domain_v1")
                < ids.index("tensile.model_support")
            )
            assert proof["options"]["end_index"] == "@source_peak_index"
            assert domain["options"]["policy"] == "effective_engineering_model_auto_v1"
            assert "tensile.prepeak_prefix" not in ids
            assert "tensile.source_support_order_guard" not in ids
            assert "tensile.terminal_domain" not in ids
            assert "tensile.source_terminal_guard_v1" not in ids

        old_methods = [
            step
            for step in old["steps"]
            if step["plugin"] in {"tensile.band_model", "tensile.model_curve"}
        ]
        new_methods = [
            step
            for step in steps
            if step["plugin"] in {"tensile.band_model", "tensile.model_curve"}
        ]
        assert new_methods == old_methods
