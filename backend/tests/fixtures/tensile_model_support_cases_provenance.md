# Model-support fixture provenance

`tensile_model_support_cases.npz` contains complete retained source frames copied
from the frozen R16 stage-array archive. It contains original engineering
strain and stress, time, source-row identity, and prepared-row identity in
acquisition order. The fixture adds no measurements, sorting, smoothing, or
zero shift.

- Source archive: `followup/16-gradual-terminal-domain/data/r16-stage-arrays.npz`
- Source archive SHA-256: `3abffb7c47622d5431c3e82ca28b24365432d03d51aad8692f29582deea7ee46`
- Independent R18 source-corpus SHA-256: `5e36230067d396bf8b41d53e26803e180f313e5d80e495c153b34384f15a97fc`
- Compact fixture SHA-256: `7f7e3766867ce6f12d15e41ac4880ab0cd27aff35658741b80bd0a832f1ba602`
- Each channel is copied from `case_<index>__lower_envelope_auto_v1__stage_01__<channel>`.

| Case | Test key | Retained rows | Purpose |
| ---: | --- | ---: | --- |
| 11 | C02APMMA | 276 | Advancing-strain stress drops do not by themselves trigger the backward-gap guard |
| 14 | M01CPMMA | 358 | First fixed paired-gap guard hold and manual-prefix boundary |
| 24 | M05APMMA | 507 | Early reversals with a guard-clear model-input candidate |
| 57 | BAM-S355-Zy4 | 1,967 | Small reversals, strict E-window parity, and manual stage-local row mapping |
| 60 | MTIL-M01A1018CR_1 | 210 | Strict-order compatibility control |
| 102 | SANDIA-304L-AD3 | 1,319 | Fixed paired-gap guard hold |
| 117 | SANDIA-304L-BT2 | 4,983 | Small reversals and guard-clear candidate |
| 141 | MTIL-C05C304_1 | 625 | Fixed paired-gap guard hold before the observed stress peak |
| 149 | MTIL-C07C304SS_1 | 604 | Fixed paired-gap guard hold before the observed stress peak |
| 152 | MTIL-M01D2024_1 | 277 | Fixed paired-gap guard hold before source proof and peak |
| 178 | MTIL-M037075_1 | 221 | Fixed paired-gap guard hold before source proof and peak |

The guard labels describe a versioned model-input boundary check. They do not
establish a measurement fault, physical event, or material-model validity.
