# Test fixture provenance

`oxford_pc_fig5_50mm_min_test2.csv` is the complete, contiguous prepared data
for the original PC50Test2 trial. The source is the [Oxford Research Archive
record](https://ora.ox.ac.uk/objects/uuid:01cf0db7-adcc-464e-9d04-3f4ccadee706),
workbook `Figure 5 Force-displacement.xlsx`, worksheet `Force-displacement`.
The source workbook SHA-256 is
`2c129056e7613f077075cf5c5b8789c2115217cae441d8aa09258fdf2ecd4cf5`.

The fixture preserves source Excel rows 3–1040 in acquisition order (1,038
observations), including the initial negative force. It is copied from
`followup/02-plastic-tensile/prepared/qualified/oxford_pc_fig5_50mm_min_test2.csv`
in the reassessment archive; the prepared file and fixture SHA-256 is
`186901368040b5776c3b1b30fdbc38cbfcd068dde6d3315d16566dd700f81f24`. The
prepared data converts force from kN to N and keeps displacement in mm and time
in seconds unchanged. The test derives engineering strain with the nominal 80
mm reference length and engineering stress with the nominal 40 mm² area; it
does not zero, clip, or otherwise adjust the measured signed force values.
