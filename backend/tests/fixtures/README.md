# Test fixture provenance

`s355_proof_point_excerpt.csv` is a small, derived excerpt from
`supplement/data-steels/prepared/BAM-S355-Zy4-extensometer.csv` in the
MatNexus-Reassessment-2026-09-21 source archive. The source file's SHA-256 is
`6a4c917ce6ae4e9748b545cff503c25b3f66aa266a4698b8e2bbd1fd5fcd5016`.

The public source is the [BAM tensile-test dataset on Zenodo, record
6778336](https://zenodo.org/records/6778336). The archive's `bam-manifest.json`
maps specimen `BAM-S355-Zy4` to the original primary-data filename `Zy4.csv`
and to the prepared file above.

The excerpt retains source data rows 438–468 and 521–527. Its
`source_physical_line` values are 440–470 and 523–529, respectively; these are
the physical-line numbers recorded in the source data, not line numbers in this
short excerpt.

The engineering strain values apply the fixture's toe correction to the measured
extensometer displacement using a 50 mm gauge length:

```text
strain_engineering = displacement_mm / 50 + 0.0004647367693135537
```

Engineering stress uses the measured 120.582838 mm² area, converted to m²:

```text
stress_engineering_pa = force_N / (120.582838e-6)
```

The excerpt also retains the source row and recorded physical-line identifiers so
the test can verify where the interpolated proof point falls in the observed data.

`tensile_terminal_v2_cases.npz` is an exact subset of the frozen prepared-source
corpus used for the R16 terminal-domain review. It copies the prepared strain,
stress, time, source-row, displacement, force, and prepared-row arrays without
resampling or correction. The source manifest SHA-256 is
`59e4b9ba1a560595890fcdaffaa10392d999e22cd7f147d3d9aa3759b543616e`; the source
corpus SHA-256 is
`5e36230067d396bf8b41d53e26803e180f313e5d80e495c153b34384f15a97fc`; the fixture
SHA-256 is `a7516023ff9ca8eacd712caa4fcd37dc5db4e0effe08ce36e3f99cf8387d64a5`.
Source-case identities and prepared-file hashes are:

| Case | Source test | Prepared SHA-256 | v1 end → reviewed v2 end |
| ---: | --- | --- | ---: |
| 85 | `NIST-U00FeDP980R01T1.405W12.7` | `f977c4cfcff237916179a7a150a5538b13108f9915152e2105591ea205b222f1` | 588 → 555 |
| 96 | `NIST-U30FeDP1180R03T1.063W12.69` | `004aa04fb80d0b59a579402d7a146c56ce44c57a8e90ca09c71fc87225805adb` | 527 → 503 |
| 107 | `SANDIA-304L-AT2` | `7d341134e4bd783e881c071ac83d7619b94d452cba780c88b8b0f7c0219e4e5b` | 4982 → 4782 |
| 118 | `SANDIA-304L-BT3` | `32a20c1a0df0f9ac11f010f8c7d7ddeef5390ddd42023906c7b75d68218b7796` | 2586 → 2586 |
| 130 | `MTIL-C02C304_1` | `35db82ea4fbe165755b06132b157116af88b302250b0b5b2029000510855e172` | 655 → 600 |
| 151 | `MTIL-M01B2024CR_1` | `0077b766a71490797804466fb492bc953ad37092b89fd66c40c639009f5a866e` | 330 → 308 |
| 60 | `MTIL-M01A1018CR_1` | `f7bbc16df02f92592212075e70abc656bdc49d90ab43110253570b4740e493d0` | 209 → 209 |

The expected ends are review references from
`MatNexus-Reassessment-2026-09-21/followup/16-gradual-terminal-domain/case-review.json`,
not physical fracture labels. Oxford PC2 is covered by the existing
`oxford_pc_fig5_50mm_min_test2.csv` fixture (case 1; 1035 → 1035).
