# Source elastic fixture provenance

`tensile_source_elastic_cases.npz` contains six complete retained source frames
selected from the frozen R16 stage-array archive for focused source-E tests. It
stores the acquired engineering strain and stress, time, source-row identity,
and prepared-row identity without sorting, filtering, or generating values.

Source artifact:

- R16 archive: `followup/16-gradual-terminal-domain/data/r16-stage-arrays.npz`
- R16 archive SHA-256: `3abffb7c47622d5431c3e82ca28b24365432d03d51aad8692f29582deea7ee46`
- Source corpus SHA-256 recorded by the R18 independent diagnostic:
  `5e36230067d396bf8b41d53e26803e180f313e5d80e495c153b34384f15a97fc`
- R18 case index order and retained row counts were cross-checked against
  `independent-source-measurement-window-cases.json`.
- Compact fixture SHA-256:
  `c415aacf986ad5bae97e532543b8d2eca4c8be3d556e65d09315522930c4ce96`

The archive uses `case_<index>__lower_envelope_auto_v1__stage_01__<channel>`
arrays as the source for each compact `c<index>_<channel>` array. All rows in
each retained frame are included:

| R18 case | Source test key | Retained rows |
| ---: | --- | ---: |
| 17 | M02CPMMA | 97 |
| 24 | M05APMMA | 507 |
| 57 | BAM-S355-Zy4 | 1,967 |
| 60 | MTIL-M01A1018CR_1 | 210 |
| 117 | SANDIA-304L-BT2 | 4,983 |
| 182 | MTIL-M05A7075_1 | 215 |

These fixtures test calculation and row provenance only. They do not establish
measurement validity or approve a material property.
