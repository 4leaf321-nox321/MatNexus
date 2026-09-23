# Tensile extras: retained-source plastic-model recipe

Use `tensile.model_anchor` when the plastic model needs a chosen offset-line
start point while Rp from the selected unmodified source prefix remains a
separate result when an observed crossing exists.
The plugin reuses the observed-intersection calculation from
`tensile.proof_stress`; it names the outputs `model_proof_stress`,
`model_proof_strain`, and `model_proof_offset`. These values describe a model
curve start. They are distinct from source Rp, which is measured on the
retained, unmodified engineering-stress prefix when the data contain an
observed crossing. They do not replace that `proof_stress` result or its
property mapping, and they do not restate measurements from the full acquired
curve.

For each new model-method recipe, save a new explicit recipe version with this
order:

1. Run `tensile.engineering` on the acquired curve without changing its row
   order. Keep the full acquired record available as the original source.
2. Run `tensile.terminal_domain` immediately after engineering conversion. It
   selects one common prefix across every channel and leaves the original
   engineering stress values unchanged.
3. Run `tensile.strength`, `tensile.elastic_modulus`,
   `tensile.proof_stress`, and `tensile.necking_candidate` on that retained
   unmodified source prefix. E and Rp are measured before any model operation;
   the retained-source E comes from unmodified engineering stress values in
   this selected domain, not from a model curve or the separately retained
   full-acquisition measurement.
4. Choose one of the seven existing model operations, then run
   `tensile.model_anchor` with the retained-source `@youngs_modulus`.
5. For the paired plastic-domain flow, run `tensile.plastic_domain` after the
   anchor and before `tensile.true_plastic`. It validates the paired model
   point and selects model rows through the chosen end, bounded by the
   retained-source necking candidate. Pass **both** validated proof values to
   `tensile.true_plastic`.
6. Keep later resampling and cropping within the selected model start and the
   unnecked range used for plastic conversion.

Store each of the seven method recipes explicitly; catalog order only controls
display and never inserts a processing stage into a pipeline. This is a new
recipe version, not an edit to historical saved recipes. Retain their full-
acquisition results separately. A `lower_yield` plateau remains a model
approximation and does not measure ReL or Lüders strain.

The terminal stage selects rows; it does not recalibrate, shift, or otherwise
modify stress. If a proof crossing existed only across the excluded terminal
collapse, the retained-source `tensile.proof_stress` result must remain
unavailable. Do not interpolate across removed rows, extrapolate, adjust E, or
reuse the historical full-acquisition Rp. After a terminal crop,
`elongation_observed` describes the retained source endpoint; it does not infer
fracture elongation. Keep the full acquired extent as separate source
provenance.

After the retained-source E and Rp steps and the chosen model operation, the
model anchor can inherit the retained-source E. The plastic-domain stage then
checks and forwards its paired stress and strain explicitly:

```json
[
  {
    "plugin": "tensile.model_anchor",
    "options": {"offset_strain": 0.002}
  },
  {
    "plugin": "tensile.plastic_domain",
    "options": {}
  },
  {
    "plugin": "tensile.true_plastic",
    "options": {
      "youngs_modulus": "@youngs_modulus",
      "proof_stress": "@plastic_domain_proof_stress",
      "proof_strain": "@plastic_domain_proof_strain"
    }
  }
]
```

The raw proof step records the 0.2% Rp calculated from the retained, unmodified
source prefix, if that prefix contains an observed crossing. The model anchor
may use another offset and operates on the selected model curve.
Pass its stress and strain together: passing stress alone can select a different
stress crossing and lose the chosen offset coordinate.

## Common model-domain step

Put `tensile.terminal_domain` immediately after `tensile.engineering` and before
`tensile.strength`, `tensile.elastic_modulus`, `tensile.proof_stress`, or
`tensile.necking_candidate`. Use this order in a new version of each of the
seven model-method recipes. The stage selects one inclusive prefix for every
channel in the current frame without changing any stress values. Thus the
following strength, E, Rp, and necking measurements use the retained, unmodified
source stress before any model approximation. The full acquired curve and
historical full-domain measurements remain separately available; the old saved
recipes are not rewritten. Later model methods still apply their own
strain-order and conversion checks.

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
included; every later row is excluded from all channels. The index refers to
the current input frame: immediately after a full `tensile.engineering` step it
matches the original acquisition row position, while an upstream crop changes
the index domain.

## Upper-envelope model curve

Choose `tensile.model_curve` when the intended model is the running maximum of
engineering stress. It is an alternative model operation to `tensile.yield_drop`;
the recipe should state which operation defines the curve. If a separate
upstream crop chooses the input domain, apply it before `tensile.terminal_domain`.
The upper-envelope step then applies `np.maximum.accumulate` to every row it
receives, raises every drop including small ones, keeps every row in that
selected prefix, and holds the last running maximum through its recorded end.
It does not rejoin a later measured tail.

The upper-envelope recipe follows engineering conversion, terminal-domain
selection, retained-source strength/E/Rp/necking, and then the model curve and
`tensile.model_anchor`. When the recipe includes
`tensile.necking_candidate`, calculate it on the retained, unmodified source
prefix after `tensile.terminal_domain` and before the model operation. The
paired model stress and strain pass through `tensile.plastic_domain` before
`tensile.true_plastic`:

```json
[
  {"plugin": "tensile.terminal_domain", "options": {}},
  {"plugin": "tensile.model_curve", "options": {}},
  {"plugin": "tensile.model_anchor", "options": {"offset_strain": 0.002}},
  {"plugin": "tensile.plastic_domain", "options": {}},
  {
    "plugin": "tensile.true_plastic",
    "options": {
      "youngs_modulus": "@youngs_modulus",
      "proof_stress": "@plastic_domain_proof_stress",
      "proof_strain": "@plastic_domain_proof_strain"
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
hook references the earlier retained-source `@youngs_modulus`. An explicitly
entered number is used as supplied, and another reference remains intact. The
anchor does not recompute E from the edited curve. Keep the retained-source E
step before the selected model operation; use an intentional numeric E only
when the recipe calls for a user-specified modulus.

The paired values remain valid through resampling and cropping only while the
model start point remains inside the retained curve. A crop that removes that
coordinate cannot be repaired by the scalar reference; the plastic conversion
will reject a point outside the curve. Keep the crop within the unnecked domain
as well, since the uniform-deformation conversion is not valid after necking.

This extension does not rewrite saved recipes or reorder their steps globally.
It also does not create a complete material-card pipeline automatically. Add
the steps to a reviewed recipe and connect the values the intended downstream
stages consume.

## Versioned retained-source recipe examples

[`recipes/valid_source_properties_v1_examples.json`](recipes/valid_source_properties_v1_examples.json)
contains seven self-contained `RecipeCreateRequest`-shaped examples, one for
each existing model method. They are explicit comparison/reference recipes for
the R14 retained-source ordering; they are not auto-installed, a new registry
kind, or universal card defaults. Before posting an object to the existing
recipes API, set `owner_workspace_slug` to the actual intended workspace slug;
omit it only for deliberate global creation by a system administrator. Then
review the created recipe's stages and options in that workspace. The frozen
comparison options include downstream resampling from zero; some real records
hold at that stage, so completion or material-card approval is not implied.
Keep the full-acquisition record and historic saved recipes unchanged. The
examples compute source strength/E/Rp/necking on the retained unmodified prefix
before the model operation. Their E and Rp use the existing automatic-E method
and 0.2% proof-line convention; a missing fit or observed crossing means that
method could not measure it on the selected prefix, not that the material
physically lacks a yield point.

The newer [`recipes/adaptive_plastic_domain_v1_examples.json`](recipes/adaptive_plastic_domain_v1_examples.json)
contains seven separate examples using `tensile.plastic_domain` after
`tensile.model_anchor`. These replace the R14 engineering resample/crop pair
with the bounded observed-row domain step, then keep the existing true-plastic,
sort, monotone and final resample stages. The examples set source
`tensile.proof_stress.search_start` to `@elastic_window_end`; this limits the
search to after the selected E window but does not validate that window as a
physically elastic interval. No fitted-origin correction is adopted by
default, and source-origin sensitivity remains unresolved in issue #30. The
new examples are comparison references, not automatic defaults or a claim of
universal material-card approval. They do not rewrite the historical R14
examples or saved recipes.

Each R15 example sets `curve.sort_unique.duplicate_policy` to `first`. The
plastic domain begins at the paired proof point, but `tensile.true_plastic` can
clip the next row to the same zero plastic strain. Keeping the first duplicate
preserves the validated proof stress as the initial table value; choosing the
last duplicate can replace it with the following row's stress. The actual PC
Test1 upper-envelope run exposed this case. The later clipped row is the one
discarded by duplicate removal; this recipe choice does not change the source
origin or establish that it is physically correct. Historical R14 recipe
examples keep their original option.

## Paired plastic-domain stage

`tensile.plastic_domain` retains the paired proof/end boundaries and every
current model row strictly between them. It adds only a missing proof or end
endpoint by linear interpolation across numeric columns. It requires at least
two current input rows after the proof point through the end before inserting
endpoints.
That count describes the frame it receives: upstream resampling does not make
those rows additional original observations. The supplied examples avoid
resampling before this stage. The inserted rows are derived coordinates and
must not be described as measured acquisition rows.

By default, the step takes the proof pair from `tensile.model_anchor`, the end
from `tensile.necking_candidate`, and the upper bound from that same necking
candidate. A reviewed manual `necking_limit` is an explicit boundary choice;
it is not an automatically measured necking value. A shorter `end_strain` is
allowed, but it cannot exceed the selected limit. The step checks the paired
proof stress against the model curve, refuses extrapolation, and rejects
negative modeled stress or strain at or below -1 inside the selected domain.
The source engineering E and Rp stages run earlier on the retained, unmodified
source prefix and remain unchanged.

Use `@plastic_domain_proof_stress` and `@plastic_domain_proof_strain` together
in `tensile.true_plastic`. That forwards the validated pair when a recipe uses
a manual model start point; the seven examples use the automatic anchor pair.
This step does not infer a physical origin, create additional observed points,
or establish that the model domain is suitable for a solver or material card.

## Scoped follow-ups

- `tensile.model_curve` supplies a full-range upper envelope with a held recorded
  tail. Existing `tensile.yield_drop` automatic profiles remain unchanged for
  saved-recipe compatibility.
- `terminal_loss_auto_v1` handles supported abrupt end losses only. Gradual or
  ambiguous endings still need review; it is not a general tail classifier or
  physical fracture detector.
