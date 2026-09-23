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

1. Calculate source-curve E and raw proof strength before changing the model
   domain or applying a model operation. If a later crop uses a
   `tensile.necking_candidate`, record it on the acquired curve first.
2. For a new model recipe, add `tensile.terminal_domain` after those source
   measurements. Then select one intended model operation: an existing
   `tensile.yield_drop` method or `tensile.model_curve`.
3. Run `tensile.model_anchor` on that model curve, using the original measured
   E, and pass **both** model references to `tensile.true_plastic`.
4. Resample or crop only when needed, retaining the model start strain and
   staying within the unnecked range used for plastic conversion.

The terminal step is explicit in new recipes; catalog order does not insert it
into a pipeline. Saved recipes keep their existing behavior. A `lower_yield`
plateau remains a model approximation and does not measure ReL or Lüders strain.

After the source E and raw Rp steps and the chosen model operation, the model
anchor can inherit the original E. The final two stages use the paired model
stress and strain explicitly:

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
model anchor may use another offset and operates on the selected model curve.
Pass its stress and strain together: passing stress alone can select a different
stress crossing and lose the chosen offset coordinate.

## Common model-domain step

Put `tensile.terminal_domain` after source E, raw Rp, and any
`tensile.necking_candidate` measurement, then before the chosen model operation.
Use it in each new recipe for the seven supported model operations. It selects
one inclusive prefix for every channel in the current frame; the original
engineering curve and its E/Rp results remain unchanged. The next model method
still applies its own strain-order and conversion checks.

The default `terminal_loss_auto_v1` only removes a supported, abrupt load loss
near the recorded end when the load does not recover. An available `time`
column is used only when its unit is seconds and its values are finite and
strictly increasing; otherwise the step falls back to strictly increasing
engineering strain, then acquisition row order. Notes identify the axis and
any fallback. Row-order progress cannot establish physical spacing. A large
sampling gap across a possible loss or a stable loaded band after it makes the
automatic end ambiguous and stops the step for review. A gradual end decline
remains in the frame and is reported as unresolved by this policy. These rules
do not identify necking or fracture.

Use `manual_end_v1` with a reviewed zero-based `end_index` when the automatic
decision is ambiguous or a different boundary is intended. The selected row is
included; every later row is excluded from all channels. Its index is relative
to the current frame, so an upstream crop changes the index domain.

## Upper-envelope model curve

Choose `tensile.model_curve` when the intended model is the running maximum of
engineering stress. It is an alternative model operation to `tensile.yield_drop`;
the recipe should state which operation defines the curve. If a separate
upstream crop chooses the input domain, apply it before `tensile.terminal_domain`.
The upper-envelope step then applies `np.maximum.accumulate` to every row it
receives, raises every drop including small ones, keeps every row in that
selected prefix, and holds the last running maximum through its recorded end.
It does not rejoin a later measured tail.

The upper-envelope recipe follows source E, raw Rp, and terminal-domain
selection with the model curve and then `tensile.model_anchor`. If a later crop
will use a
`tensile.necking_candidate`, calculate the candidate on the acquired curve
before applying `tensile.terminal_domain`. The paired model stress and strain
still go to `tensile.true_plastic`:

```json
[
  {"plugin": "tensile.terminal_domain", "options": {}},
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
selected model operation; use an intentional numeric E only when the recipe
calls for a user-specified modulus.

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
- `terminal_loss_auto_v1` handles supported abrupt end losses only. Gradual or
  ambiguous endings still need review; it is not a general tail classifier or
  physical fracture detector.
