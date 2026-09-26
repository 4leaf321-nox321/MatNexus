"""Ensure tensile extension values fit the persisted summary-key column."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from matcore import extensions, processing, registry
from matcore.processing import Frame, Step

BACKEND = Path(__file__).resolve().parents[2]
EXTENSIONS = BACKEND / "extensions"
FIXTURE = BACKEND / "tests" / "fixtures" / "tensile_isotonic_terminal_join_cases.npz"
CHANNEL_UNITS = {
    "force": "N",
    "displacement": "m",
    "time": "s",
    "source_row": "1",
    "prepared_row": "1",
    "strain_engineering": "1",
    "stress_engineering": "Pa",
    "model_input_index": "1",
}

extensions.load(EXTENSIONS)
processing.load_builtin()


def test_tensile_extension_produced_keys_fit_summary_storage() -> None:
    produced = [
        (plugin.id, item.key)
        for plugin in registry.list_plugins()
        if plugin.id.startswith("tensile.")
        for item in (*plugin.makes_values, *plugin.makes_columns)
    ]

    assert produced
    assert all(len(key) <= 50 for _plugin_id, key in produced), [
        (plugin_id, key, len(key)) for plugin_id, key in produced if len(key) > 50
    ]


def test_observed_isotonic_rescue_emits_only_bounded_diagnostic_keys() -> None:
    prefix = "c085_"
    with np.load(FIXTURE, allow_pickle=False) as saved:
        columns = {key: saved[prefix + key].copy() for key in CHANNEL_UNITS}
        elastic_end = float(saved[prefix + "source_elastic_end_index"][0])
    frame = Frame(columns, dict(CHANNEL_UNITS))
    plugin = registry.get("tensile.band_model")

    result = processing.apply(
        [
            Step(
                plugin.id,
                {
                    "policy": "band_and_source_events_auto_v1",
                    "method": "isotonic",
                    "source_elastic_end_index": elastic_end,
                    "source_index_column": "model_input_index",
                },
            )
        ],
        frame,
    )

    stage = result.stages[-1]
    values = {scalar.key: scalar.value for scalar in stage.scalars}
    expected_keys = {
        "band_model_source_iso_released_anchor_count",
        "band_model_source_iso_max_abs_distortion",
        "band_model_source_iso_remaining_unedited_declines",
    }

    assert plugin.version == "4"
    assert expected_keys <= values.keys()
    assert all(len(key) <= 50 for key in values)
    assert values["band_model_source_event_isotonic_trigger_count"] == 1.0
    assert values["band_model_source_event_isotonic_fit_region_count"] >= 1.0
    assert values["band_model_source_event_isotonic_changed_points"] > 0.0
    assert values["band_model_source_iso_max_abs_distortion"] > 0.0
    assert values["band_model_source_iso_remaining_unedited_declines"] >= 0.0
