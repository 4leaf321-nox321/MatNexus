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
   yield-drop editing. This records the measured values against the acquired
   engineering curve.
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

- Check the upper-yield automatic result against protected terminal-tail cases;
  a mismatch remains open for a separate bounded change.
- The event detector identifies drop and recovery events. It is not a classifier
  for plateau duration or slope; that needs a separately specified rule.
