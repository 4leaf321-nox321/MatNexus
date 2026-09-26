# Source-event fixture provenance

`tensile_source_event_cases.npz` contains authentic retained engineering frames
from the frozen R18 source-path validation artifact. Each frame is the input to
the source-E stage after the existing terminal-domain selection. The fixture
copies available channels in their current acquisition order and includes the
independently recorded source-E end row; it adds no measurements or edits.

- Source array archive: `source-path-validation-stage-arrays.npz`
- Source array archive SHA-256: `ee66c4668d2b962324b59657c1ae7cd4340f1ec9b259de386b76268625418fea`
- Corrected source-path result SHA-256: `cad9492dc24af79c7741bccbb006f7bf25bb781182d3b5b742bf4612f4b445b8`
- Source-manifest SHA-256: `5632db582dcaa89520de62933160a6b26ebca56fb2c494a64e313829d642d1df`
- Source-corpus SHA-256: `5e36230067d396bf8b41d53e26803e180f313e5d80e495c153b34384f15a97fc`
- Compact fixture SHA-256: `360a5d3c8cf63a976ebee7f5f7b6f5182237d9acd92eaeae93b43f798beacc2a`
- Channels are copied from `case_<index>__lower_envelope_auto_v1__stage_03__<channel>`.
- `source_elastic_end_index` is copied from that case's source-E stage scalar.

| Case | Source test key | Purpose |
| ---: | --- | --- |
| 11 | C02APMMA | No-band compatibility comparison; source-E prefix remains measured data |
| 52 | BAM-S355-Zx3 | Recovered event wholly within source-E prefix |
| 55 | BAM-S355-Zy2 | Recovered event wholly within source-E prefix |
| 56 | BAM-S355-Zy3 | Recovered event wholly within source-E prefix |
| 101 | SANDIA-304L-AD2 | Recovered event wholly within source-E prefix |
| 109 | SANDIA-304L-AT4 | Recovered event wholly within source-E prefix |
| 110 | SANDIA-304L-BD1 | Recovered event wholly within source-E prefix |
| 112 | SANDIA-304L-BD3 | Recovered event wholly within source-E prefix |
| 113 | SANDIA-304L-BR1 | Recovered event wholly within source-E prefix |
| 114 | SANDIA-304L-BR2 | Recovered event wholly within source-E prefix |
| 117 | SANDIA-304L-BT2 | Recovered event wholly within source-E prefix |
| 121 | SANDIA-304L-CD2 | Recovered event wholly within source-E prefix |
| 124 | SANDIA-304L-CT1 | Recovered event wholly within source-E prefix |
| 125 | SANDIA-304L-CT3 | Source-E ends at row 326; the last retained row at or before it is 325 |
| 126 | SANDIA-304L-CT4 | Recovered event wholly within source-E prefix |

The event fits in the tests are recomputed from the copied source frames. The
earlier R18 validation outputs are provenance, not expected values for the new
policy.
