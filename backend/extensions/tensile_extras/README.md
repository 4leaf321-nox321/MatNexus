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

## Original-row elastic measurement foundation

`tensile.source_elastic_modulus` measures E on the current input frame before
any model operation and returns that whole frame unchanged. Its default
`auto_rows_v1` finds the first maximum engineering stress, takes the pre-peak
rows in the 10–40% stress band, and fits the inclusive original-row envelope
from the first to last band member. It never sorts, drops, smooths, or shifts
rows. When the complete strain input is strictly increasing, it delegates to
the existing `tensile.elastic_modulus` auto calculation and preserves its
scalars and notes. Otherwise it performs centered OLS on every row in the
source envelope in acquisition order, including local strain reversals, with
the existing minimum-row, numerical, positive-slope, and R² guards.

Select `manual_rows` to provide inclusive `start_index` and `end_index` values
for the current input frame. Manual windows use the same fit guards; their row
indices are not claimed to be original CSV line numbers. `source_elastic_*`
outputs record the selected current-input row bounds and the number of
nonincreasing strain steps inside the fitted interval. `elastic_window_start`
and `elastic_window_end` describe the minimum and maximum strain actually
included in the fit.

The E channel options default only when omitted. An explicitly empty, false,
non-string, or whitespace-only channel name is an error; it never falls back to
the engineering channel silently.

## Original-row proof stress

`tensile.source_proof_stress` measures Rp from the unchanged current input
frame. Its default `first_positive_forward_v1` policy evaluates
`d[i] = stress[i] - E * (strain[i] - offset)` without adding the E-fit
intercept or shifting the origin. A crossing must be between adjacent original
rows, both inside the inclusive row and strain bounds, with the right strain
strictly greater than the left. It selects the first interpolated positive
stress; a falling stress segment remains eligible. It never sorts, smooths,
filters rows, bridges a gap, or extrapolates.

When omitted, E, the starting row, and the starting strain refer to
`@youngs_modulus`, `@source_elastic_end_index`, and `@elastic_window_end`.
The ending row defaults to the last current-input row; the ending strain
defaults to the observed maximum over the selected row interval. Direct E and
explicit manual search bounds are supported. Effective options store the
resolved numeric inputs for JSON replay. Output row indices always refer to
the current input frame, not file line numbers.

If no eligible positive crossing exists, the step raises a processing error
with the search bounds and separately defined forward-pair, reverse/equal-
strain crossing, positive/nonpositive candidate, and coincident-residual
counts. The failed stage does not emit Rp, so dependent model stages stop too.
When two adjacent residuals are exactly zero, the segment uses its left
observed point (`t=0`); coincident segments are reported as a subset of the
positive or nonpositive forward candidates. This remains an observed
intersection rule, not an approval of measurement validity or material
properties.

The source-elastic stage remains an E foundation only. Neither source E nor
source Rp approves measurement validity or material properties, changes
historical recipes, or relaxes the downstream model and plastic-domain checks.
Manual E workflows and their saved settings remain available.

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

For a new recipe that needs to screen a gradual terminal decline, select
`terminal_loss_auto_v2` explicitly. It first runs the unchanged v1 abrupt-loss
decision, then fits a continuous one-knot line to uniformly spaced values of
the selected engineering-stress channel over the late progress window. A
supported negative post-knot slope can move the inclusive end earlier to the
greatest original row at or before the fitted knot. Interpolated fit values are
scoring points only; the stage returns only original rows and leaves every
channel unchanged. A positive pre-knot slope is allowed.

The v2 fit requires a usable, strictly increasing time or strain progress axis;
when only acquisition row order is available it keeps the v1 end and reports
that gradual onset is unavailable. It also keeps the v1 end when original-row
support or progress spans are sparse, the knot depends too much on fit-window
start, the near-optimal knot range is broad, a significant sampling gap
intersects a scored window, load recovers after half the candidate-to-end loss,
or a stable loaded suffix remains. These are hold reasons, not data repair.
The 3% positive-peak stress-loss gate is a frozen conservative profile value
from the reviewed finite corpus, not a universal material threshold. The
effective options record all v2 constants so saved runs can be replayed.

Decision code `3` means the approximate accelerated-terminal-loss onset was
selected. V2 diagnostics include the v1 end, candidate row, fit slopes and SSE
gain, peak- and local-stress loss, original support, gap/recovery/suffix checks,
and a near-optimal knot range. The detrended late MAD describes fit-residual
spread; it is not a sensor-noise estimate. A smooth decline without a distinct
accelerating onset remains at the v1 end. When substantial preterminal loss
exists but no onset is accepted, the neutral
`substantial_preterminal_loss_no_distinct_onset` diagnostic does not distinguish
a continuous decline from a long loaded plateau. The selected boundary
describes a model-record domain; it does not identify the first infinitesimal
decrease, physical fracture, necking, or the validity of the remaining tail for
a material model.

The seven R15 model-method reference examples are preserved. New explicit v2
copies, with their other processing stages and options unchanged, are in
[`recipes/progressive_terminal_domain_v2_examples.json`](recipes/progressive_terminal_domain_v2_examples.json).

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

R18's separate [`recipes/source_measurement_model_v1_examples.json`](recipes/source_measurement_model_v1_examples.json)
keeps source strength, source-row E and observed source Rp ahead of model
selection. It adds `tensile.model_support` after the source necking candidate
and before either stable-band or upper-envelope modeling. The R17 examples and
saved recipes remain unchanged. The follow-up
[`recipes/source_measurement_model_v2_examples.json`](recipes/source_measurement_model_v2_examples.json)
changes only the six stable-band steps to the explicit source-event policy;
its upper-envelope control and downstream steps remain the same.

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

## Original-row model support

`tensile.model_support` creates a separate model-input frame from the current
engineering curve. It keeps the first row in the chosen inclusive current-row
range, then keeps a later row only when its strain exceeds the last retained
strain. It applies the same original indices to every channel and adds
`model_input_index`; that column identifies rows only at this stage. Later
interpolation or resampling can make its values fractional, so it is not a
source-row identity downstream.

Before that projection, `record_high_guarded_v1` examines every original gap.
For a gap it compares backward strain `dx` with the unloading-equivalent strain
`u = max(0, (stress_anchor − stress_gap) / E)` and residual `r = dx − u`. It
withholds the model path when `r` exceeds the larger of one E-window strain
span and six scaled residual MADs divided by E, while `u` is below one tenth of
`dx`. These fixed heuristic limits are a model-boundary review; they do not
diagnose a sensor fault, prove noise, or certify a material model. A flagged
automatic input stops without silently cropping it.

Optional `start_index` and `end_index` values select an explicit model scope;
they do not recompute source E or Rp. Gaps inside that scope still receive the
same guard. Notes record when a manual scope cuts a flagged full-input boundary
or omits source E rows, the observed proof pair, or the full-input peak. The
first maximum-stress row inside the chosen scope must remain selected. The
source frame itself is unchanged.

## Stable-band model stage

`tensile.band_model` is the versioned R17 model-region choice for sources whose
original retained engineering curve contains a supported post-peak band. It
must follow source strength/E/Rp measurement and precede `tensile.model_anchor`.
It reads strictly increasing `strain_engineering` and `stress_engineering` in
`1` and `Pa`; a usable time column in seconds may provide the selector's
progress axis. It never sorts or edits the source frame in place.

The automatic policy `band_and_events_auto_v1` uses the frozen row-count,
normalized-span, stress-level, range and gap limits recorded in the effective
options. These are conservative selection settings, not material constants.
When it finds no band, it delegates the unmodified input to the same method's
legacy `*_auto_v1` profile, preserving that method's curve result. Explicit v1
recipes retain that numerical behavior. An unsupported candidate or infeasible
selected fit stops with a reason; it does not switch to a different method.
`manual_band_v1` takes inclusive current-frame
`band_start`/`band_end` row positions. The end row is the observed right anchor,
so at least two fit-core rows must precede it. Optional `peak_row` and
`left_anchor` overrides still have to satisfy the loading guard and observed
crossing rules.

The registered automatic default is `band_and_events_auto_v2`. It keeps the
same selector, methods and source statistics as v1. If a full-recovery event
starts in the selected band and recovers by its observed right anchor, v2 fits
through that event's recorded end row; it does not extend the boundary for an
open/terminal event or a recovery outside the band. For `lower_envelope` only,
an anchor-only failure on a closed recovered event can retry as one original-
source suffix-minimum fit over the connected prior modeled component and closed
source events. Whole components and source bounds are retained; open or terminal
events cannot connect the composition. A missing feasible source anchor remains
an explicit failure. The `model_end_index` scalar reports the actual right
observed anchor of the band-connected model component after either v2
composition; separately fitted event endpoints remain in their own event
records and do not extend this band scalar.

The separate `band_and_source_events_auto_v1` policy keeps the same selected-
band calculation as v2. Its source-event fitting applies when no band is found
and the method is `median_plateau`, `linear`, `least_squares`, or
`robust_linear`. It maps the source-E end row through the required
`model_input_index` channel, then excludes closed recovered events whose
complete observed interval lies in that measured prefix. It fits eligible
later events from their full original cores with the existing observed-anchor
helper. If that helper cannot fit an eligible closed-recovery component, the
policy can retry the same method with fixed observed anchors and only the
interior rows that the fit can change. For an E-crossing component, the mapped
E-prefix end P and the component's observed right endpoint R bound the edit;
the original event bounds remain in diagnostics. A one-row interior uses only
the method's bounded scalar objective (or anchor interpolation for `linear`),
so no slope or fit-quality statistic is reported. Other bounded fits retain the
method-specific objective and must satisfy the same observed-anchor constraints;
an infeasible fit remains an explicit hold. A non-crossing event with no
eligible strict-target left anchor may use the nearest original observed anchor
after the preservation boundary whose stress does not exceed the event's right
anchor, provided the affected rows do not overlap a protected terminal interval.
A closed crossing with no editable row (`R=P+1`) is kept as an unchanged, diagnosed
`crossing_no_editable_rows` event when its observed boundary stresses are
ordered; that completion row is protected from later event fits. Terminal and
observation-open events remain unchanged. If no retained row falls inside the E
prefix, the first current model row is retained as the scope anchor; if the
whole scope is inside the prefix, the stage returns unchanged input with a
no-eligible-event diagnostic. The original v1/v2 policies retain their
existing `lower_envelope` and `isotonic` no-band paths. Under this source-event
policy, isotonic first preserves a successful legacy no-band result exactly.
Only after that legacy step raises does a separate raw-topology gate allow a
bounded isotonic terminal join: one closed recovered source-event component
must end at the observed start `T` of a protected terminal drop, and unbounded
equal-row PAVA on the original rows through `T` must raise the raw stress at
`T` into the following decline. The rescue recomputes every eligible closed
component from original stress, closes overlapping modeled influences, and
uses the latest admissible observed left anchor `L` at or after the mapped E
boundary with `y[L] ≤ y[R]`. Equal-row PAVA applies only to open rows
`L+1..R-1` and is clipped to the raw anchor stresses. The E prefix, protected
terminal rows, outer anchors, and all rows outside declared open intervals
remain unchanged. Missing topology or infeasible anchors remain an explicit
hold with the legacy reason recorded; no error text selects the rescue. This
policy does not smooth measurements, validate an elastic window, or imply that
a stress drop inside the E prefix is noise.

Choose one method explicitly: `lower_envelope` uses source suffix minima;
`isotonic` uses equal-row PAVA across the full influence; `median_plateau` uses
the original band-core median; `linear` joins the observed anchors without
fitting the band interior; `least_squares` uses a bounded equal-row affine fit;
and `robust_linear` uses the bounded fixed-scale Huber fit. The left observed
anchor can differ between methods. Selected-band support statistics remain
based on original band-core rows. Median, OLS and Huber fit objectives use
their actual recorded fit core; eligible v2 full-recovery completion may
extend that core through `R_model − 1`. The observed-row bridge from the left
anchor is reported as part of model influence. These choices may lower the
recorded peak in the model curve; that is a modeling choice, not a measured
lower-yield strength.

The stage detects source drop/recovery events once on the unchanged stress
array. Events fully inside a band are handled by its selected method. A
disjoint recovered event can be fitted only inside its original-row cell; other
recovered events crossing the band influence are an explicit hold. One closed
partial-recovery topology is composed with the band when its rows satisfy
`L ≤ peak ≤ trough < rebound < band_start ≤ R < end`. The band then covers only
through that anchor. In v1, its continuation remains original input for later
disjoint event fits, whose declared influence may edit its loading bridge; it is
not relabeled as full recovery. In v2, a later closed eligible event that cannot
find a lower-envelope anchor may join the connected band/event component for a
single original-source refit. An unrecovered terminal event outside the
influence remains observed.
A successful fit preserves both observed anchors and every stress row outside
its open influence interval. Later raw decreases outside edited regions may
remain, so the full model curve is not necessarily globally monotone.

The fixed `band_model_*` scalars report the peak, selected band, method-specific
left anchor, source support, normalized span/gap, changed-row count, peak-row
depression and maximum stress change. V2 also reports released internal anchors,
composition count, additional changed rows and maximum additional stress change.
For lower compositions, the added-row diagnostics compare the final composed
output on each newly included open span with that pool's pre-pool baseline. A
later connected pool may change an earlier added span, so these values describe
the final curve rather than an isolated step-by-step delta.
Notes distinguish source core rows from the edited influence and name event
decisions. They do not classify fracture, approve a physical yield point, or
establish solver suitability.

Two decimated PC4 lower-profile holds remain under review because component
connectivity is sensitive to a sampled one-row gap and exact ties. This is a
sampling/tie sensitivity of the current connection rule, not a finding of
arithmetic infeasibility or proof that the experiment is noisy. No smoothing
or permissive connector has been added.

[`recipes/stable_band_model_v1_examples.json`](recipes/stable_band_model_v1_examples.json)
contains seven explicit v1 comparison recipes. The matching
[`recipes/stable_band_model_v2_examples.json`](recipes/stable_band_model_v2_examples.json)
contains v2 recipes. In each set, six methods replace only the R16 `yield_drop`
stage; the upper-envelope control keeps its unchanged `tensile.model_curve`
stage. Both preserve the R16 source-proof and downstream stage ordering and do
not replace historical examples or saved recipes.

## Effective model card-domain stage

Use `tensile.effective_card_domain` after `tensile.model_anchor` and before
`tensile.true_plastic` when a new recipe should extend its plastic-card domain
through the model's right-side effect support. Its default policy,
`uniform_measured_v1`, ends at the same source necking candidate as the existing
`tensile.plastic_domain`; it does not require method-effect diagnostics. Choose
`effective_engineering_model_auto_v1` to end at the later of that source
candidate and `@model_card_effect_end_index`, or choose
`manual_observed_end_v1` to include a reviewed current-frame `end_index`.
Automatic mode validates the effect index, its exact observed strain, and the
model-input row count, then includes the selected or edited right support in the
chosen end. This is right-end coverage only; the stage does not prove complete
proof-to-band coverage. Independently verify that each selected band starts at
or after proof and that its start/end and every changed post-proof row lie
inside the card's proof-to-end interval. Report a coverage failure if a band
starts before proof. Manual mode reports when the observed end precedes a known
model-effect end.

The model methods expose six common `model_card_*` values. Band fits include the
right support of each changed declared interval and the selected band end, even
when the selected values equal the source. Methods without typed legacy
intervals use the row after the last changed curve value as a changed-curve
closure, capped at the final retained row; this is not described as an internal
fit anchor. A genuine no-op without a selected band reports effect index `-1`
and strain `0`.

The registered coordinate assumption is fixed to
`effective_engineering_to_true_uniform_v1`. Extending the card beyond the source
necking candidate is an explicitly saved simulation approximation that maps
effective engineering strain into the uniform-deformation true coordinate. It
does not mean measured local stress or constant true stress after necking. The
stage keeps the source necking candidate as a separate scalar and sets the
delegated `plastic_domain` computational limit to the selected card end. The
wrapper labels `plastic_domain_necking_limit` as the card computation cap;
`card_domain_source_necking_strain` retains the source candidate separately. It
retains `plastic_domain_*` diagnostics and all of that step's checks for paired
proof values, observed support, interpolation, units, input values and selected
nonnegative engineering stress. An interpolated end is reported with index `-1`
and is not assigned an acquisition-row identity.

The seven R19 examples in
[`recipes/effective_card_domain_v1_examples.json`](recipes/effective_card_domain_v1_examples.json)
copy the R18 source-measurement v2 structures and change only the domain step,
recipe identifiers, labels and descriptions. The existing downstream
`tensile.true_plastic`, `curve.sort_unique`, `curve.monotone`, and 300-point
`curve.resample` operations remain explicit and unchanged. Their clipping,
sorting, duplicate selection, monotone lift, and final plastic-axis range still
affect what reaches the exported table. This is a numerical transfer under a
saved coordinate assumption, not evidence that every final card row is a
constitutive measurement.

## Scoped follow-ups

- `tensile.model_curve` supplies a full-range upper envelope with a held recorded
  tail. Existing `tensile.yield_drop` automatic profiles remain unchanged for
  saved-recipe compatibility.
- `tensile.band_model` is a versioned stable-region approximation, not a general
  material softening or terminal-onset classifier. Use explicit v1 when
  reproducing the earlier numerical policy.
- `terminal_loss_auto_v1` handles supported abrupt end losses only. Gradual or
  ambiguous endings still need review; it is not a general tail classifier or
  physical fracture detector.
