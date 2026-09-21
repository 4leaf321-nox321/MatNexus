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
