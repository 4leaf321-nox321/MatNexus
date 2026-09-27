"""The v3 source-order examples differ from v2 only at the explicit E step."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from matcore import extensions, processing, registry

RECIPES = Path(__file__).resolve().parents[1] / "tensile_extras" / "recipes"
extensions.load(RECIPES.parents[1])
processing.load_builtin()


def _recipe_method(recipe: dict[str, object]) -> str:
    steps = recipe["steps"]
    assert isinstance(steps, list)
    for step in steps:
        assert isinstance(step, dict)
        if step["plugin"] in {"tensile.band_model", "tensile.model_curve"}:
            options = step["options"]
            assert isinstance(options, dict)
            return str(options["method"])
    raise AssertionError("recipe has no explicit model method")


@pytest.mark.parametrize("profile", ["uniform", "tail"])
def test_v3_seven_method_examples_change_only_the_explicit_e_step(profile: str) -> None:
    v2 = json.loads(
        (RECIPES / f"source_order_{profile}_v2_examples.json").read_text(encoding="utf-8")
    )
    v3 = json.loads(
        (RECIPES / f"source_order_{profile}_v3_examples.json").read_text(encoding="utf-8")
    )

    assert v3["schema"] == f"matnexus.tensile.source_order_{profile}_v3_examples/1"
    assert len(v2["recipes"]) == len(v3["recipes"]) == 7
    assert len({recipe["key"] for recipe in v3["recipes"]}) == 7
    v2_methods = {_recipe_method(recipe) for recipe in v2["recipes"]}
    v3_methods = {_recipe_method(recipe) for recipe in v3["recipes"]}
    assert len(v2_methods) == len(v3_methods) == 7
    assert v3_methods == v2_methods

    old_top = deepcopy(v2)
    new_top = deepcopy(v3)
    for document in (old_top, new_top):
        document.pop("schema")
        document.pop("description")
        document.pop("recipes")
    assert new_top == old_top

    top_description = v3["description"].lower()
    assert "opt-in" in top_description and "candidate" in top_description
    assert "physical-validity approval" in top_description
    assert "not material-card approved" in top_description
    assert "solver approved" in top_description
    assert "not defaults" in top_description

    for old, new in zip(v2["recipes"], v3["recipes"], strict=True):
        assert new["key"] == old["key"].replace("_v2_", "_v3_")
        assert new["label"] == old["label"]
        assert new["test_type_key"] == old["test_type_key"]
        old_metadata = deepcopy(old)
        new_metadata = deepcopy(new)
        for recipe in (old_metadata, new_metadata):
            recipe.pop("key")
            recipe.pop("description")
            recipe.pop("steps")
        assert new_metadata == old_metadata

        description = new["description"].lower()
        assert "opt-in" in description and "candidate" in description
        assert "physical validity" in description and "not approved" in description
        assert "not material-card approved" in description
        assert "solver approved" in description
        assert "not a default" in description

        old_steps = deepcopy(old["steps"])
        new_steps = new["steps"]
        old_e_steps = [
            step for step in old_steps if step["plugin"] == "tensile.source_elastic_modulus_v2"
        ]
        new_e_steps = [
            step for step in new_steps if step["plugin"] == "tensile.source_elastic_modulus_v3"
        ]
        assert len(old_e_steps) == len(new_e_steps) == 1
        assert old_e_steps[0]["options"] == {"policy": "auto_rows_v2"}
        old_e_steps[0]["plugin"] = "tensile.source_elastic_modulus_v3"
        old_e_steps[0]["options"]["policy"] = "auto_rows_v3"
        assert new_steps == old_steps

        for step in new_steps:
            registry.get(step["plugin"])


def test_v3_examples_are_explicit_and_do_not_change_default_e_registration() -> None:
    legacy = registry.get("tensile.source_elastic_modulus")
    legacy_policy = next(param for param in legacy.params if param.name == "policy")
    assert legacy_policy.default == "auto_rows_v1"

    v2 = registry.get("tensile.source_elastic_modulus_v2")
    v2_policy = next(param for param in v2.params if param.name == "policy")
    assert v2_policy.default == "auto_rows_v2"

    for profile in ("uniform", "tail"):
        v2_examples = json.loads(
            (RECIPES / f"source_order_{profile}_v2_examples.json").read_text(encoding="utf-8")
        )
        for recipe in v2_examples["recipes"]:
            e_step = next(
                step
                for step in recipe["steps"]
                if step["plugin"].startswith("tensile.source_elastic_modulus")
            )
            assert e_step == {
                "plugin": "tensile.source_elastic_modulus_v2",
                "options": {"policy": "auto_rows_v2"},
            }


def test_v3_metadata_describes_the_selected_fit_window_and_v2_is_unchanged() -> None:
    v2_values = {
        value.key: value
        for value in registry.get("tensile.source_elastic_modulus_v2").makes_values
    }
    v3_values = {
        value.key: value
        for value in registry.get("tensile.source_elastic_modulus_v3").makes_values
    }

    assert v2_values["elastic_support_member_count"].label == "자동 띠 원행 지지점 수"
    assert "v2의 10~40%" in v2_values["elastic_support_member_count"].help
    assert v2_values["elastic_loo_min_r_squared"].label == "고정 원행 LOO 최소 R²"

    assert v3_values["elastic_support_member_count"].label == "선택 E 창 원행 지지점 수"
    assert "첫 연속 통과 구간" in v3_values["elastic_support_member_count"].help
    assert v3_values["elastic_loo_min_r_squared"].label == "선택 E 창 고정 원행 LOO 최소 R²"
    assert "첫 연속 통과 구간" in v3_values["elastic_loo_min_r_squared"].help
    assert v3_values["elastic_loo_failed_row"].label.startswith("선택 E 창")
