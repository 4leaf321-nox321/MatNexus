# Tensile extras: source-first plastic-model recipe

Use `tensile.model_anchor` when the plastic model needs a chosen offset-line start
point while the Rp calculated from the original curve remains available as its
own result.
The plugin reuses the observed-intersection calculation from
`tensile.proof_stress`; it names the outputs `model_proof_stress`,
`model_proof_strain`, and `model_proof_offset`. These values describe a model
curve start. They are not the Rp calculated from the original curve and do not
replace the original `proof_stress` result or its property mapping.

Keep the recipe source-first:

1. Calculate the source-curve elastic modulus and raw proof strength before any
   yield-drop editing. If a later crop will use a `tensile.necking_candidate`,
   record that candidate on the acquired curve before editing too. This records
   the measured values against the acquired engineering curve.
2. Apply the selected `tensile.yield_drop` operation. An explicit `lower_yield`
   plateau is a model approximation and does not measure ReL or Lüders strain.
3. Run `tensile.model_anchor` on the resulting model curve.
4. Resample or crop if needed, while retaining the model start strain in the
   curve and staying within the unnecked range used for plastic conversion.
5. Pass **both** model references to `tensile.true_plastic`.

After the source E and raw Rp steps, followed by the chosen yield-drop operation,
the model anchor can inherit the original E. The final two stages use the paired
model stress and strain explicitly:

```json
[
  {
    "plugin": "tensile.model_anchor",
    "options": {"offset_strain": 0.002}
  },
  {
    "plugin": "tensile.true_plastic",
    "options": {
      "youngs_modulus": "@youngs_modulus",
      "proof_stress": "@model_proof_stress",
      "proof_strain": "@model_proof_strain"
    }
  }
]
```

The raw proof step records the 0.2% Rp calculated from the original curve. The
model anchor may use another offset and operates on the post-edit model curve.
Pass its stress and strain together: passing stress alone can select a different
stress crossing and lose the chosen offset coordinate.

## Upper-envelope model curve

Choose `tensile.model_curve` when the intended model is the running maximum of
engineering stress. It is an alternative model operation to `tensile.yield_drop`;
the recipe should state which operation defines the curve. For a selected input
domain, run the existing `curve.crop` before `tensile.model_curve`. The step
applies `np.maximum.accumulate` to every row it receives, raises every drop
including small ones, keeps every row, and holds the last running maximum through
the recorded end. It does not rejoin a later measured tail.

The upper-envelope recipe follows the source E and raw Rp steps with the model
curve and then `tensile.model_anchor`. If a later crop will use a
`tensile.necking_candidate`, calculate the candidate on the acquired curve
before applying `tensile.model_curve`. The paired model stress and strain still
go to `tensile.true_plastic`:

```json
[
  {"plugin": "tensile.model_curve", "options": {}},
  {"plugin": "tensile.model_anchor", "options": {"offset_strain": 0.002}},
  {
    "plugin": "tensile.true_plastic",
    "options": {
      "youngs_modulus": "@youngs_modulus",
      "proof_stress": "@model_proof_stress",
      "proof_strain": "@model_proof_strain"
    }
  }
]
```

This step does not calculate E, Rp, or source-proof outputs. Its peak diagnostics
report the selected input stress maximum and its strain, plus its zero-based row
position in the current input frame (not the source Excel row). A negative
initial engineering-stress value is preserved by the envelope.
`tensile.true_plastic` rejects any negative stress in its input before applying
its proof-point crop, so prepare the source or crop to a suitable range when full
conversion is intended; the recipe snippet is not valid for every source curve.

The running maximum also propagates an isolated high artifact through all later
rows. Peak diagnostics show where that input maximum occurs, but this method does
not judge whether it is physically valid.

The held tail is an engineering-stress plateau. It does not assert constant true
stress or physical perfect plasticity. The model ends at the last recorded row;
that row is not inferred to be fracture. Keep plastic conversion within the
unnecked range.

When `youngs_modulus` is omitted from the anchor options, its local preparation
hook references the earlier `@youngs_modulus`. An explicitly entered number is
used as supplied, and another reference remains intact. The anchor does not
recompute E from the edited curve. Keep the original measured E step before the
yield-drop operation; use an intentional numeric E only when the recipe calls
for a user-specified modulus.

The paired values remain valid through resampling and cropping only while the
model start point remains inside the retained curve. A crop that removes that
coordinate cannot be repaired by the scalar reference; the plastic conversion
will reject a point outside the curve. Keep the crop within the unnecked domain
as well, since the uniform-deformation conversion is not valid after necking.

This extension does not rewrite saved recipes or reorder their steps globally.
It also does not create a complete material-card pipeline automatically. Add
the steps to a reviewed recipe and connect the values the intended downstream
stages consume.

## Scoped follow-ups

- `tensile.model_curve` supplies a full-range upper envelope with a held recorded
  tail. Existing `tensile.yield_drop` automatic profiles remain unchanged for
  saved-recipe compatibility.
- The event detector identifies drop and recovery events. It is not a classifier
  for plateau duration or slope; that needs a separately specified rule.
