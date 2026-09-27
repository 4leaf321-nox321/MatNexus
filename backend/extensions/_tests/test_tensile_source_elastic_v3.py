"""Focused tests for the opt-in first-passage source-E v3 candidate."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from matcore import extensions, processing, registry
from matcore.processing import Frame, ProcessingError, Step, apply

EXTENSIONS = Path(__file__).resolve().parents[1]
extensions.load(EXTENSIONS)
processing.load_builtin()

from matnexus_ext.tensile_extras import source_elastic  # noqa: E402


def _frame(
    strain: list[float], stress: list[float], source_rows: list[int] | None = None
) -> Frame:
    rows = source_rows if source_rows is not None else list(range(len(strain)))
    values = {
        "strain_engineering": np.asarray(strain, dtype=np.float64),
        "stress_engineering": np.asarray(stress, dtype=np.float64),
        "source_row": np.asarray(rows, dtype=np.float64),
    }
    return Frame(
        values,
        {
            "strain_engineering": "1",
            "stress_engineering": "Pa",
            "source_row": "1",
        },
    )


def _values(result: object) -> dict[str, float]:
    stage = result.stages[-1]  # type: ignore[attr-defined]
    return {item.key: item.value for item in stage.scalars}


def _run(frame: Frame, plugin: str, policy: str):
    return apply([Step(plugin, {"policy": policy})], frame)


def _snapshot(frame: Frame) -> tuple[dict[str, str], dict[str, bytes]]:
    return dict(frame.units), {key: value.tobytes() for key, value in frame.columns.items()}


# Exact R55 prepared-array values for M11APMMA input rows 5--103, followed by
# its measured first raw peak. Keeping the complete v2 window reproduces the
# v2 hold; the first 23 rows are the actual 10--40% first passage.
_M11_ROWS = """0.0019690000000000003, 7116318.4088246338
0.002362, 8370505.0330235092
0.0027500000000000003, 9602862.4596493021
0.0031260000000000003, 10849111.193821603
0.0035170000000000002, 12057654.950367672
0.0038810000000000003, 13220555.839260934
0.0042450000000000005, 14363612.003087755
0.0046160000000000003, 15476901.079314923
0.0049870000000000001, 16548516.23290257
0.0053140000000000001, 17550674.848757684
0.0056440000000000006, 18503221.651946705
0.0059589999999999999, 19420047.950016137
0.0062550000000000001, 20261464.292833101
0.0065260000000000006, 21035408.57042418
0.006783, 21710129.222683068
0.0070030000000000005, 22345160.424809083
0.0072270000000000008, 22880968.001602907
0.0074110000000000009, 23377086.128263853
0.0075769999999999995, 23813670.079725489
0.0077339999999999996, 24210564.581054244
0.0079000000000000008, 24587614.357316565
0.0080370000000000007, 24924974.683446009
0.0081630000000000001, 25222645.55944258
0.0082719999999999998, 25480626.98530627
0.008379000000000001, 25718763.686103527
0.0084679999999999998, 25917210.936767906
0.0085620000000000002, 26095813.462365847
0.0086470000000000002, 26234726.537830912
0.0086840000000000007, 26333950.163163103
0.0087220000000000006, 26393484.338362414
0.0087550000000000006, 26393484.338362414
0.0088000000000000005, 26413329.063428853
0.0087860000000000004, 26393484.338362414
0.0087889999999999999, 26333950.163163103
0.0087919999999999995, 26294260.713030227
0.0087889999999999999, 26234726.537830912
0.0088040000000000011, 26195037.087698035
0.0087810000000000006, 26135502.912498724
0.0087819999999999999, 26075968.737299409
0.0087799999999999996, 26016434.562100094
0.0087730000000000013, 25976745.111967221
0.0087680000000000015, 25937055.661834344
0.0087410000000000005, 25857676.761568591
0.0087360000000000007, 25758453.136236403
0.0087019999999999997, 25679074.23597065
0.0086969999999999999, 25579850.610638462
0.008679000000000001, 25500471.710372709
0.008652, 25381403.359974083
0.0086169999999999997, 25282179.734641891
0.0085970000000000005, 25202800.834376141
0.008575000000000001, 25103577.20904395
0.0085559999999999994, 25024198.3087782
0.0085360000000000002, 24964664.133578885
0.0085050000000000004, 24885285.233313136
0.0084910000000000003, 24786061.607980944
0.0084400000000000013, 24607459.082383003
0.0083940000000000004, 24448701.2818515
0.008319, 24210564.581054244
0.0082319999999999997, 23912893.705057677
0.0081320000000000003, 23575533.378928233
0.0079970000000000006, 23158794.152533036
0.0078650000000000005, 22742054.926137842
0.0077480000000000005, 22384849.87494196
0.0076909999999999999, 22206247.349344019
0.0076480000000000003, 22126868.449078266
0.0076450000000000008, 22146713.174144704
0.0076740000000000011, 22245936.799476892
0.0077359999999999998, 22444384.050141271
0.0078000000000000005, 22682520.750938527
0.0078869999999999999, 22940502.176802218
0.0079660000000000009, 23178638.877599474
0.0080359999999999997, 23436620.303463168
0.0081110000000000002, 23635067.554127548
0.0081960000000000002, 23873204.2549248
0.0082529999999999999, 24071651.50558918
0.0083280000000000003, 24250254.031187121
0.0083800000000000003, 24409011.831718624
0.0084320000000000003, 24528080.182117254
0.0084770000000000002, 24627303.807449441
0.0084920000000000013, 24686837.982648756
0.0085290000000000001, 24766216.882914506
0.0085770000000000013, 24825751.058113821
0.008568000000000001, 24885285.233313136
0.0086060000000000008, 24944819.408512447
0.0086390000000000008, 25004353.583711762
0.0086660000000000001, 25044043.033844639
0.0086829999999999997, 25083732.483977515
0.0086779999999999999, 25083732.483977515
0.0086909999999999991, 25083732.483977515
0.0086890000000000005, 25143266.659176826
0.0087160000000000015, 25143266.659176826
0.008712000000000001, 25103577.20904395
0.0087060000000000002, 25103577.20904395
0.0086760000000000014, 25063887.758911077
0.0086670000000000011, 25083732.483977515
0.0087349999999999997, 25083732.483977515
0.0086510000000000007, 25024198.3087782
0.0086169999999999997, 25044043.033844639
0.0086440000000000006, 25202800.834376141"""
_M11_PEAK_STRAIN = 0.030310000000000004
_M11_PEAK_STRESS = 63126070.43633898


def _m11_apmma_frame() -> Frame:
    measured = np.fromstring(_M11_ROWS.replace(",", " "), sep=" ").reshape(-1, 2)
    strain = [*measured[:, 0], _M11_PEAK_STRAIN]
    stress = [*measured[:, 1], _M11_PEAK_STRESS]
    source_rows = [*range(5, 104), 175]
    return _frame(strain, stress, source_rows)


def test_v3_uses_m11apmma_first_passage_only_after_v2_hold_and_replays() -> None:
    frame = _m11_apmma_frame()
    before = _snapshot(frame)

    v2 = _run(
        frame,
        "tensile.source_elastic_modulus_v2",
        source_elastic.AUTO_POLICY_V2,
    )
    assert "youngs_modulus" not in _values(v2)
    assert _values(v2)["elastic_r_squared"] == pytest.approx(0.9776182133195495)

    result = _run(
        frame,
        "tensile.source_elastic_modulus_v3",
        source_elastic.AUTO_POLICY_V3,
    )
    values = _values(result)
    stage = result.stages[-1]
    notes = " ".join(stage.notes)

    assert values["youngs_modulus"] == pytest.approx(2.921290156165144e9)
    assert values["source_elastic_start_index"] == 0.0
    assert values["source_elastic_end_index"] == 22.0
    assert values["source_elastic_v3_candidate_start_index"] == 0.0
    assert values["source_elastic_v3_candidate_end_index"] == 22.0
    assert values["elastic_v3_candidate_point_count"] == 23.0
    assert values["elastic_r_squared"] == pytest.approx(0.9984875637084134)
    assert values["elastic_loo_min_r_squared"] == pytest.approx(0.998366798169849)
    assert values["source_elastic_v3_fallback_attempted_code"] == 1.0
    assert values["source_elastic_v3_fallback_used_code"] == 1.0
    assert "첫 통과 구간 [0, 22]" in notes
    assert "물리적으로 타당한 Young's modulus로 승인된 값이 아닙니다" in notes
    assert stage.options == {
        "policy": source_elastic.AUTO_POLICY_V3,
        "strain": "strain_engineering",
        "stress": "stress_engineering",
    }
    assert _snapshot(frame) == before

    replay = apply([Step("tensile.source_elastic_modulus_v3", dict(stage.options))], frame)
    assert _values(replay) == values
    assert replay.stages[-1].notes == stage.notes
    assert replay.stages[-1].options == stage.options


def test_v3_holds_bt3_first_passage_with_nonmonotone_source_rows() -> None:
    # Compact reproduction from rows in the actual SANDIA-304L-BT3 first
    # 10--40% passage. Source identifiers retain the sampled row identities.
    strain = [
        0.00034309943878769094,
        0.0003407624393951773,
        0.0004131932814403091,
        0.00040935411958666816,
        0.00035960849211026365,
        0.00038023211507134095,
        0.0015209816775923091,
        0.1,
    ]
    stress = [
        72115443.77952756,
        72115443.77952756,
        72703661.1023622,
        71115474.33070865,
        70115504.88188978,
        70880187.40157479,
        266403625.51181105,
        677273425.5118111,
    ]
    frame = _frame(strain, stress, [92, 93, 94, 95, 96, 97, 331, 2566])
    before = _snapshot(frame)

    result = _run(
        frame,
        "tensile.source_elastic_modulus_v3",
        source_elastic.AUTO_POLICY_V3,
    )
    values = _values(result)
    notes = " ".join(result.stages[-1].notes)

    assert "youngs_modulus" not in values
    assert values["source_elastic_v3_fallback_attempted_code"] == 1.0
    assert values["source_elastic_v3_fallback_used_code"] == 0.0
    assert values["source_elastic_v3_candidate_start_index"] == 0.0
    assert values["source_elastic_v3_candidate_end_index"] == 6.0
    assert "응력" in notes and "엄격히 증가하지 않음" in notes
    assert "변형률" in notes and "엄격히 증가하지 않음" in notes
    assert _snapshot(frame) == before


def test_v3_holds_first_band_run_instead_of_skipping_to_later_eligible_run() -> None:
    stress = [0.0, 0.20, 0.25, 0.41, 0.10, 0.16, 0.22, 0.28, 0.34, 0.40, 1.0]
    strain = [index * 0.001 for index in range(len(stress))]
    frame = _frame(strain, [value * 1e9 for value in stress])

    result = _run(
        frame,
        "tensile.source_elastic_modulus_v3",
        source_elastic.AUTO_POLICY_V3,
    )
    values = _values(result)
    notes = " ".join(result.stages[-1].notes)

    assert "youngs_modulus" not in values
    assert values["source_elastic_v3_candidate_start_index"] == 1.0
    assert values["source_elastic_v3_candidate_end_index"] == 2.0
    assert values["source_elastic_v3_fallback_used_code"] == 0.0
    assert "시작 응력이 최대응력의 15%보다 큼" in notes
    assert "끝 응력이 최대응력의 35%보다 작음" in notes
    # Rows 4--9 form a later six-row monotone passage, but v3 must not use it.
    assert all(np.diff(strain[4:10]) > 0)
    assert all(np.diff(stress[4:10]) > 0)


def test_v3_preserves_a_v2_e_even_when_its_window_has_a_stress_reversal() -> None:
    frame = _frame(
        [0.001, 0.002, 0.002001, 0.004, 0.005, 0.006, 0.007],
        [0.2e9, 0.3e9, 0.29999e9, 0.5e9, 0.6e9, 0.7e9, 2.0e9],
    )
    v2 = _run(
        frame,
        "tensile.source_elastic_modulus_v2",
        source_elastic.AUTO_POLICY_V2,
    )
    result = _run(
        frame,
        "tensile.source_elastic_modulus_v3",
        source_elastic.AUTO_POLICY_V3,
    )

    v2_values = _values(v2)
    values = _values(result)
    assert all(values[key] == value for key, value in v2_values.items())
    assert values["source_elastic_v3_fallback_attempted_code"] == 0.0
    assert values["source_elastic_v3_fallback_used_code"] == 0.0
    assert "그 결과를 그대로 유지했습니다" in " ".join(result.stages[-1].notes)
    assert result.stages[-1].notes[: len(v2.stages[-1].notes)] == v2.stages[-1].notes


def test_v3_is_opt_in_and_does_not_change_legacy_or_v2_choices() -> None:
    legacy = registry.get("tensile.source_elastic_modulus")
    legacy_params = {item.name: item for item in legacy.params}
    assert legacy_params["policy"].choices == ("auto_rows_v1", "manual_rows")
    assert legacy_params["policy"].default == "auto_rows_v1"

    v2 = registry.get("tensile.source_elastic_modulus_v2")
    v2_params = {item.name: item for item in v2.params}
    assert v2_params["policy"].choices == ("auto_rows_v2",)
    assert v2_params["policy"].default == "auto_rows_v2"

    v3 = registry.get("tensile.source_elastic_modulus_v3")
    v3_params = {item.name: item for item in v3.params}
    assert v3_params["policy"].choices == ("auto_rows_v3",)
    assert v3_params["policy"].default == "auto_rows_v3"
    assert "start_index" not in v3_params

    with pytest.raises(ProcessingError, match="auto_rows_v1, manual_rows"):
        apply(
            [Step("tensile.source_elastic_modulus", {"policy": "auto_rows_v3"})],
            _frame([0.001, 0.002], [1.0, 2.0]),
        )
