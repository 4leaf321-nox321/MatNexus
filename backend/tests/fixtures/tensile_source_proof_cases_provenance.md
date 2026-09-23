# Source-proof fixture provenance

This fixture contains unchanged retained source arrays from the frozen R16 stage-array archive. It contains no invented measurements, sorting, smoothing, or zero shift. Each record preserves the full retained input frame and original row order for strain, stress, time, source-row, and prepared-row channels.

Source archive: `followup/16-gradual-terminal-domain/data/r16-stage-arrays.npz`

Source archive SHA-256: `3abffb7c47622d5431c3e82ca28b24365432d03d51aad8692f29582deea7ee46`
Independent source-corpus SHA-256: `5e36230067d396bf8b41d53e26803e180f313e5d80e495c153b34384f15a97fc`

Each array is copied from `case_<index>__lower_envelope_auto_v1__stage_01__<channel>` and renamed `c<index>_<channel>`:

| Case index | Rows | Test purpose |
| ---: | ---: | --- |
| 5 | 218 | PLA no-crossing control |
| 17 | 97 | Missing source-E control; proof step must remain unavailable |
| 23 | 130 | M04 retained-tail boundary no-crossing control |
| 24 | 507 | Positive source-proof crossing |
| 30 | 52 | M06 crossing-before-search no-crossing control |
| 57 | 1,967 | Positive source-proof crossing and strict-E parity control |
| 60 | 210 | Positive source-proof crossing and strict-E parity control |
| 117 | 4,983 | Positive source-proof crossing and nonstrict-W E control |

The five saved-E proof holds (5, 6, 7, 23, 30) and their zero eligible crossings are documented in the independent R18 `proof-residual-analysis.json` and its review. Positive crossing expectations for 24, 57, 60, and 117 are pinned to the R18 independent source-path candidate calculations. Case 17 deliberately remains without an E output under the configured automatic band. These fixtures verify numerical and software behavior; they do not establish physical material validity.
