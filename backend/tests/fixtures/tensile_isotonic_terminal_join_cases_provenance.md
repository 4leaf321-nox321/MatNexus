# Isotonic terminal-join fixture provenance

`tensile_isotonic_terminal_join_cases.npz` contains nine authentic retained
`tensile.model_support` frames copied from the frozen R18 v1 source-path
validation artifacts. Four cases are the previously held isotonic targets;
five are accepted-v1 controls. Input channels and current row order are copied
unchanged. The fixture adds only frozen source-property scalars and, for the
five accepted controls, the v1 output stress used for exact compatibility
checks.

- Source results: `source-path-validation-results.json`
- Source results SHA-256: `cad9492dc24af79c7741bccbb006f7bf25bb781182d3b5b742bf4612f4b445b8`
- Source stage arrays: `source-path-validation-stage-arrays.npz`
- Source stage arrays SHA-256: `ee66c4668d2b962324b59657c1ae7cd4340f1ec9b259de386b76268625418fea`
- Compact fixture SHA-256: `5c1c00812bd2ae1efdf96e191a71afff8cc62b993b823f3db9ce19feb8bd4cc5`
- Copied model-support channels: `force`, `displacement`, `time`, `source_row`,
  `prepared_row`, `strain_engineering`, `stress_engineering`, and
  `model_input_index`.
- Source E/proof scalars are copied from the same accepted v1 record. No
  measurements, event labels, or fitted arrays are synthesized.

| Case | Role |
| ---: | --- |
| 85, 107, 113, 122 | Frozen isotonic rescue targets; v1 stopped at the band-model stage |
| 0, 9, 11, 151, 156 | Accepted-v1 selected-band, terminal-only, and recovered-event compatibility controls |

The fixture preserves the saved v1 control stress arrays for exact comparison.
Target output values are not stored as expected results; their observed-event
membership, bounded anchors, and objective are checked from source evidence.
The raw-gate feasibility witness's lower-control-derived candidate anchors are
evidence that a bounded solution exists, not prescribed isotonic anchors. In
case 113, the final independently audited automatic terminal component is
`2526..4556` with observed anchors `2524` and `4557`; the witness candidate
`2492..4557` belongs to a distinct earlier-component closure and is not the
selected terminal fit region.
