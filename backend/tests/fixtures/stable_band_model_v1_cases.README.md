# Stable-band model fixture provenance

`stable_band_model_v1_cases.npz` contains the original corpus arrays for six
recorded R16 input prefixes. The arrays are copied without numeric conversion
from the frozen validation corpus, then sliced inclusively through each
`newR16.endIndex` so the test input matches the frame after the existing
`tensile.terminal_domain` step. NPZ keys retain their corpus `cNNN_` prefixes;
`x`, `y`, `time`, row identifiers, displacement, force and prepared-row arrays
are included where present. Tests do not refer to the corpus's external path.

Source `corpus.npz` SHA-256:
`5e36230067d396bf8b41d53e26803e180f313e5d80e495c153b34384f15a97fc`.

Source `manifest.json` SHA-256:
`5632db582dcaa89520de62933160a6b26ebca56fb2c494a64e313829d642d1df`.

The R16 inclusive end rows come from
`followup/16-gradual-terminal-domain/data/r16-terminal-comparison.json`.
The prepared CSV hashes and original row counts below come from the source
manifest. The NPZ in this repository has SHA-256
`632d1995bc49732546711ebbf426df061da657d63260ba3988d6b612ec9ec16f`.

| Corpus index | Source test key | Prepared CSV SHA-256 | Source rows | R16 end row | Fixture rows |
| ---: | --- | --- | ---: | ---: | ---: |
| 0 | `oxford_pc_fig5_50mm_min_test1` | `537fd378d2c83567f873b961b3a7a13ff9afdeae9d12f3d07d4acd31dbeda68c` | 1068 | 1066 | 1067 |
| 2 | `oxford_pc_fig5_50mm_min_test3` | `fdc2ddd133dbf1042fb8b5fe5807f3aea93f265fdf24371514acf8f3acdc5a0c` | 2180 | 2178 | 2179 |
| 4 | `oxford_pc_fig5_5mm_min_test2` | `3229a4a3cdefcfc611601b15af6a3c16cde1d3f6bb8131ff28cd4aff5f7ca95f` | 2017 | 2015 | 2016 |
| 9 | `C01APMMA` | `b398a8ed25e9950d35248a2437dd6fd15ba4ea2696c13e5968b572181cdc3ffe` | 212 | 210 | 211 |
| 26 | `M05DPMMA` | `4de5092344029c4ccc0607a445ff74d2011f283a3aa6c9b4c3fd11bc14cc0ca4` | 495 | 493 | 494 |
| 27 | `ME05CPMMA` | `7b103e1f39137c9a88677cf151797b5fbb0b23eb31c216b2494b694e15a4c600` | 572 | 570 | 571 |
| 151 | `MTIL-M01B2024CR_1` | `0077b766a71490797804466fb492bc953ad37092b89fd66c40c639009f5a866e` | 332 | 308 | 309 |

Case 4 is the PC composition regression: a closed partial episode rebounds before
the selected band and its detector end lies after the band, followed by separate
events. Case 151 exercises no-band same-method compatibility on a recovered
metal curve. Case 9 is the continuous-decline/no-band control. The PC and PMMA
prefixes exercise the six separate band methods on recorded inputs. The existing
`tensile_terminal_v2_cases.npz` fixture supplies non-strict BT3 case 118.
