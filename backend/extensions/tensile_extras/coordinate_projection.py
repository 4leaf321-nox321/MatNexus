"""Bounded post-fit projection for true-plastic coordinate order.

This module deliberately has no frame, registry, or database dependency.  It
works on paired engineering-strain/stress arrays and returns a new stress
array.  Rows for which the model did not change the source are fixed anchors;
the projection only moves an edited model value toward its source value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import ArrayLike, NDArray

from matcore.processing import ProcessingError

DEFAULT_METHOD: Final[str] = "bounded"
LOWER_ENVELOPE_METHOD: Final[str] = "lower_envelope"
METHODS: Final[tuple[str, ...]] = (
    DEFAULT_METHOD,
    LOWER_ENVELOPE_METHOD,
    "isotonic",
    "median_plateau",
    "linear",
    "least_squares",
    "robust_linear",
)
_METHOD_ALIASES: Final[dict[str, str]] = {
    "lower_envelope_auto_v1": LOWER_ENVELOPE_METHOD,
    "upper_envelope": DEFAULT_METHOD,
    "upper_envelope_auto_v1": DEFAULT_METHOD,
    "isotonic_auto_v1": "isotonic",
    "median_plateau_auto_v1": "median_plateau",
    "linear_auto_v1": "linear",
    "least_squares_auto_v1": "least_squares",
    "robust_linear_auto_v1": "robust_linear",
}
_ROUNDING_FACTOR: Final[float] = 128.0


@dataclass(frozen=True, slots=True)
class ProjectionDiagnostics:
    """Summary of rows changed by one projection call."""

    changed_count: int
    max_abs_change: float
    first_affected_row: int | None
    last_affected_row: int | None

    @property
    def count(self) -> int:
        """Short alias useful to callers displaying a compact summary."""

        return self.changed_count

    @property
    def max_change(self) -> float:
        """Short alias for :attr:`max_abs_change`."""

        return self.max_abs_change

    @property
    def affected_first_row(self) -> int | None:
        """Short alias for :attr:`first_affected_row`."""

        return self.first_affected_row

    @property
    def affected_last_row(self) -> int | None:
        """Short alias for :attr:`last_affected_row`."""

        return self.last_affected_row


def project_model_stress(
    engineering_strain: ArrayLike,
    raw_stress: ArrayLike,
    modeled_stress: ArrayLike,
    youngs_modulus: float,
    proof_strain: float,
    method: str | None = None,
    end_strain: float | None = None,
) -> tuple[NDArray[np.float64], ProjectionDiagnostics]:
    """Project a modeled engineering-stress curve into valid true-plastic order.

    ``engineering_strain`` must already be strictly increasing.  True-plastic
    coordinate order constrains adjacent rows with both strains greater than
    ``proof_strain``.  If ``end_strain`` is provided, both rows must also be
    at or below that upper eligibility cutoff.  A correction additionally
    preserves every originally nondecreasing engineering-stress pair touching
    a corrected row, including seams outside that coordinate domain.  The
    derived coordinate is

    ``log1p(strain) - stress * (1 + strain) / youngs_modulus``.

    The editable mask is exactly ``modeled_stress != raw_stress``.  Every other
    row remains bit-for-bit fixed.  An editable value is constrained to the
    closed interval between its raw and original modeled values.  Thus a
    projection cannot increase model distortion.  With ``method=None`` the
    generic bounded projection is used.  ``lower_envelope`` adds the
    method-specific condition that the projected stress is no greater than the
    raw stress.  The other methods retain the same bounded original-region
    interval, but do not add that lower-envelope bound.

    A ``ProcessingError`` is raised when fixed rows already violate the
    downstream order, when an editable region has no feasible anchor, or when
    floating-point verification cannot prove the requested strict order.
    """

    strain = _vector(engineering_strain, "engineering_strain")
    raw = _vector(raw_stress, "raw_stress")
    modeled = _vector(modeled_stress, "modeled_stress")
    try:
        modulus = float(youngs_modulus)
        proof = float(proof_strain)
        end = float(end_strain) if end_strain is not None else None
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(
            "coordinate projection modulus, proof strain, and end strain must be real numbers."
        ) from None
    _validate_inputs(strain, raw, modeled, modulus, proof, end)
    resolved_method = _resolve_method(method)

    editable = modeled != raw
    original_x = _derived_coordinate(strain, modeled, modulus)
    active = (strain[:-1] > proof) & (strain[1:] > proof)
    if end is not None:
        active &= (strain[:-1] <= end) & (strain[1:] <= end)
    eligible = np.zeros(strain.size, dtype=bool)
    eligible[:-1] |= active
    eligible[1:] |= active
    editable_target = editable & eligible

    # A fixed/fixed pair has no degrees of freedom.  Diagnose it before any
    # interval calculation so a later editable run cannot hide the source row.
    for left in np.flatnonzero(active):
        right = int(left) + 1
        left_index = int(left)
        if (
            not editable[left_index]
            and not editable[right]
            and not original_x[right] > original_x[left_index]
        ):
            _raise_pair(
                "fixed-fixed true-plastic order violation",
                left_index,
                right,
                original_x[left_index],
                original_x[right],
            )

    # A completed model is already the downstream contract.  In particular,
    # do not introduce a new engineering-stress-shape failure into a curve
    # whose true-plastic coordinate is valid; this is also what preserves a
    # bit-exact no-op for existing modeled curves.
    coordinate_valid = all(
        original_x[int(left) + 1] > original_x[int(left)] for left in np.flatnonzero(active)
    )
    lower_bound_valid = not (
        resolved_method == LOWER_ENVELOPE_METHOD and np.any(editable_target & (modeled > raw))
    )
    if coordinate_valid and lower_bound_valid:
        return modeled.copy(), _diagnostics(modeled, modeled)

    # Engineering-stress shape is a separate constraint from the downstream
    # coordinate order.  A correction can touch a proof/end seam even when
    # that pair is outside the coordinate domain, so retain every originally
    # nondecreasing pair that touches a row we may edit.  An original reversal
    # is historical data and must not become an error merely because the
    # neighboring row is editable.
    shape_pair = (modeled[1:] >= modeled[:-1]) & (editable_target[:-1] | editable_target[1:])

    scaled_raw, scaled_modeled = _scaled_bounds(raw, modeled, modulus)
    lower = np.where(eligible, np.minimum(scaled_raw, scaled_modeled), scaled_modeled)
    upper = np.where(eligible, np.maximum(scaled_raw, scaled_modeled), scaled_modeled)
    if resolved_method == LOWER_ENVELOPE_METHOD:
        # The intersection with [min(raw, model), max(raw, model)] is a
        # singleton when model > raw, and otherwise leaves the original
        # interval unchanged.  It is intentionally exact and closed.
        upper = np.where(eligible, np.minimum(upper, scaled_raw), scaled_modeled)
    if np.any(lower > upper):  # defensive: the construction above is closed
        row = int(np.flatnonzero(lower > upper)[0])
        raise ProcessingError(
            f"coordinate projection row {row}: empty original bounded interval."
        )

    coefficients = 1.0 + strain
    logs = np.log1p(strain)
    safe_difference = np.full(active.shape, np.nan, dtype=np.float64)
    for left in np.flatnonzero(active):
        right = int(left) + 1
        safe_difference[left] = _safe_coordinate_difference(
            logs,
            coefficients,
            int(left),
            right,
            lower,
            upper,
        )

    # A reachable suffix is represented by one closed interval per row.  The
    # recurrence is O(n): with y_j in [L_j, U_j], the left endpoint must be
    # large enough to reach L_j through the coordinate inequality, while the
    # right endpoint is limited by U_j when stress shape is active.  When both
    # constraints apply, y_left <= y_right and coordinate order together also
    # imply y_left <= D / (c_right - c_left).
    reachable_lower = lower.copy()
    reachable_upper = upper.copy()
    for left in range(strain.size - 2, -1, -1):
        if not active[left] and not shape_pair[left]:
            continue
        right = left + 1
        # Fixed/fixed rows were verified above and need no projection
        # interval.  Skipping them also avoids imposing a larger safety margin
        # on a pair that cannot be edited.
        if not editable_target[left] and not editable_target[right]:
            continue
        new_lower = reachable_lower[left]
        new_upper = reachable_upper[left]
        if active[left]:
            candidate_lower = (
                coefficients[right] * reachable_lower[right] - safe_difference[left]
            ) / coefficients[left]
            # Keep an inverse-boundary roundoff from moving an editable value
            # one ULP above its original modeled value.  Forward propagation
            # and exact verification still enforce the coordinate inequality.
            candidate_lower = np.nextafter(candidate_lower, -np.inf)
            new_lower = max(new_lower, candidate_lower)
        if shape_pair[left]:
            candidate_upper = reachable_upper[right]
            if active[left]:
                candidate_upper = min(
                    candidate_upper,
                    safe_difference[left] / (coefficients[right] - coefficients[left]),
                )
            new_upper = min(new_upper, candidate_upper)
        reachable_lower[left] = new_lower
        reachable_upper[left] = new_upper
        if not new_lower <= new_upper:
            _raise_interval(left, right, new_lower, new_upper)

    chosen = np.empty_like(scaled_modeled)
    chosen_lower = np.empty_like(scaled_modeled)
    chosen_upper = np.empty_like(scaled_modeled)
    for row in range(strain.size):
        local_lower = reachable_lower[row]
        local_upper = reachable_upper[row]
        if (
            row > 0
            and (active[row - 1] or shape_pair[row - 1])
            and (editable_target[row - 1] or editable_target[row])
        ):
            previous = row - 1
            if active[previous]:
                local_upper = min(
                    local_upper,
                    (coefficients[previous] * chosen[previous] + safe_difference[previous])
                    / coefficients[row],
                )
            if shape_pair[previous]:
                local_lower = max(local_lower, chosen[previous])
        if not local_lower <= local_upper:
            # The backward inverse can round an exactly reachable editable
            # boundary one ULP above the forward image.  Moving that editable
            # predecessor toward the interior repairs the inverse mismatch;
            # fixed rows and source/model bounds remain untouched.  The exact
            # coordinate check below is the final authority.
            if row > 0 and active[row - 1] and editable_target[row - 1]:
                previous = row - 1
                # If the shape lower bound is the active side, move the
                # predecessor down.  If the right-row lower bound is active,
                # move it up to increase the coordinate upper bound.  Rebuild
                # both sides after each ULP so neither inverse is stale.
                move_down = shape_pair[previous] and (chosen[previous] > reachable_lower[row])
                direction = -np.inf if move_down else np.inf
                for _ in range(16):
                    nudged = np.nextafter(chosen[previous], direction)
                    if not (
                        nudged >= chosen_lower[previous]
                        and nudged <= chosen_upper[previous]
                        and nudged >= lower[previous]
                        and nudged <= upper[previous]
                    ):
                        break
                    chosen[previous] = nudged
                    local_lower = reachable_lower[row]
                    if shape_pair[previous]:
                        local_lower = max(local_lower, chosen[previous])
                    local_upper = reachable_upper[row]
                    if active[previous]:
                        local_upper = min(
                            local_upper,
                            (
                                coefficients[previous] * chosen[previous]
                                + safe_difference[previous]
                            )
                            / coefficients[row],
                        )
                    if local_lower <= local_upper:
                        break
            if not local_lower <= local_upper and row > 0 and active[row - 1]:
                previous = row - 1
                candidate = local_lower
                candidate_is_editable = editable_target[row]
                candidate_in_bounds = candidate <= upper[row] and (
                    candidate_is_editable or candidate == scaled_modeled[row]
                )
                shape_ok = not shape_pair[previous] or candidate >= chosen[previous]
                left_coordinate = logs[previous] - coefficients[previous] * chosen[previous]
                right_coordinate = logs[row] - coefficients[row] * candidate
                if candidate_in_bounds and shape_ok and right_coordinate > left_coordinate:
                    # The algebraic inverse was rounded inward, but the
                    # candidate pair itself still has a strict derived-
                    # coordinate gap.  Keep that exact feasible boundary and
                    # let final verification enforce the physical contract.
                    local_upper = candidate
            if not local_lower <= local_upper:
                _raise_interval(row - 1, row, local_lower, local_upper)

        value = min(max(scaled_modeled[row], local_lower), local_upper)
        if editable_target[row] and value == local_lower:
            nudged = np.nextafter(value, np.inf)
            if nudged <= local_upper and nudged <= upper[row]:
                value = nudged
        if (
            editable_target[row]
            and row < active.size
            and active[row]
            and shape_pair[row]
            and value == local_upper
        ):
            nudged = np.nextafter(value, -np.inf)
            if nudged >= local_lower and nudged >= lower[row]:
                value = nudged
        chosen_lower[row] = local_lower
        chosen_upper[row] = local_upper
        if not editable_target[row] and value != scaled_modeled[row]:
            _raise_interval(row - 1, row, local_lower, local_upper)
        chosen[row] = scaled_modeled[row] if not editable_target[row] else value

    projected = modeled.copy()
    for row in np.flatnonzero(editable_target):
        index = int(row)
        # Preserve an unchanged editable endpoint exactly.  Multiplication by
        # E after a divide can otherwise turn a no-op into a one-bit change.
        if chosen[index] == scaled_modeled[index]:
            continue
        with np.errstate(over="ignore", invalid="ignore"):
            value = float(chosen[index] * modulus)
        if not np.isfinite(value):
            raise ProcessingError(
                f"coordinate projection row {index}: projected stress is not finite."
            )
        value = min(
            max(value, min(raw[index], modeled[index])),
            max(raw[index], modeled[index]),
        )
        if resolved_method == LOWER_ENVELOPE_METHOD:
            value = min(value, raw[index])
        projected[index] = value

    _verify_projection(
        strain=strain,
        raw=raw,
        modeled=modeled,
        projected=projected,
        modulus=modulus,
        active=active,
        shape_pair=shape_pair,
        editable=editable_target,
        method=resolved_method,
    )
    return projected, _diagnostics(modeled, projected)


def _resolve_method(method: str | None) -> str:
    value = DEFAULT_METHOD if method is None else method
    if not isinstance(value, str):
        raise ProcessingError(
            f"coordinate projection method must be one of {METHODS}; got {value!r}."
        )
    resolved = _METHOD_ALIASES.get(value, value)
    if resolved not in METHODS:
        names = ", ".join(METHODS)
        raise ProcessingError(
            f"unsupported coordinate projection method {value!r}; choose {names}."
        )
    return resolved


def _vector(value: ArrayLike, name: str) -> NDArray[np.float64]:
    try:
        raw = np.asarray(value)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(
            f"coordinate projection {name} must be a numeric vector."
        ) from None
    if raw.ndim != 1 or np.iscomplexobj(raw):
        raise ProcessingError(
            f"coordinate projection {name} must be a one-dimensional real vector."
        )
    try:
        numeric = np.asarray(raw, dtype=np.float64)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(
            f"coordinate projection {name} must be a numeric vector."
        ) from None
    if not np.all(np.isfinite(numeric)):
        raise ProcessingError(f"coordinate projection {name} contains a non-finite value.")
    return numeric


def _validate_inputs(
    strain: NDArray[np.float64],
    raw: NDArray[np.float64],
    modeled: NDArray[np.float64],
    modulus: float,
    proof: float,
    end: float | None,
) -> None:
    if strain.size == 0:
        raise ProcessingError("coordinate projection requires at least one row.")
    if raw.size != strain.size or modeled.size != strain.size:
        raise ProcessingError(
            "coordinate projection strain, raw stress, and modeled stress must "
            "have equal lengths."
        )
    if not np.isfinite(modulus) or modulus <= 0.0:
        raise ProcessingError(
            "coordinate projection Young's modulus must be finite and positive."
        )
    if not np.isfinite(proof):
        raise ProcessingError("coordinate projection proof strain must be finite.")
    if end is not None and not np.isfinite(end):
        raise ProcessingError("coordinate projection end strain must be finite when provided.")
    if np.any(strain <= -1.0):
        row = int(np.flatnonzero(strain <= -1.0)[0])
        raise ProcessingError(
            f"coordinate projection row {row}: engineering strain must be greater than -1."
        )
    if not np.all(np.isfinite(1.0 + strain)):
        row = int(np.flatnonzero(~np.isfinite(1.0 + strain))[0])
        raise ProcessingError(
            f"coordinate projection row {row}: 1 + engineering strain is not finite."
        )
    bad = np.flatnonzero(np.diff(strain) <= 0.0)
    if bad.size:
        row = int(bad[0])
        raise ProcessingError(
            f"coordinate projection rows {row}->{row + 1}: engineering strain "
            "is not strictly increasing."
        )


def _derived_coordinate(
    strain: NDArray[np.float64], stress: NDArray[np.float64], modulus: float
) -> NDArray[np.float64]:
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        coordinate = np.log1p(strain) - stress * (1.0 + strain) / modulus
    if not np.all(np.isfinite(coordinate)):
        raise ProcessingError(
            "coordinate projection derived true-plastic coordinate is not finite."
        )
    return coordinate


def _scaled_bounds(
    raw: NDArray[np.float64], modeled: NDArray[np.float64], modulus: float
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        scaled_raw = raw / modulus
        scaled_modeled = modeled / modulus
    if not np.all(np.isfinite(scaled_raw)) or not np.all(np.isfinite(scaled_modeled)):
        raise ProcessingError("coordinate projection stress/E bounds are not finite.")
    return scaled_raw, scaled_modeled


def _safe_coordinate_difference(
    logs: NDArray[np.float64],
    coefficients: NDArray[np.float64],
    left: int,
    right: int,
    lower: NDArray[np.float64],
    upper: NDArray[np.float64],
) -> float:
    difference = float(logs[right] - logs[left])
    scale = max(
        1.0,
        abs(float(logs[left])),
        abs(float(logs[right])),
        abs(float(coefficients[left] * lower[left])),
        abs(float(coefficients[left] * upper[left])),
        abs(float(coefficients[right] * lower[right])),
        abs(float(coefficients[right] * upper[right])),
    )
    delta = _ROUNDING_FACTOR * np.finfo(np.float64).eps * scale
    safe = float(np.nextafter(difference - delta, -np.inf))
    if not np.isfinite(safe) or safe <= 0.0:
        _raise_pair(
            "strict-order roundoff margin exhausted",
            left,
            right,
            difference,
            delta,
        )
    return safe


def _verify_projection(
    *,
    strain: NDArray[np.float64],
    raw: NDArray[np.float64],
    modeled: NDArray[np.float64],
    projected: NDArray[np.float64],
    modulus: float,
    active: NDArray[np.bool_],
    shape_pair: NDArray[np.bool_],
    editable: NDArray[np.bool_],
    method: str,
) -> None:
    if not np.array_equal(projected[~editable], modeled[~editable]):
        raise ProcessingError("coordinate projection changed a fixed source row.")
    lower = np.minimum(raw, modeled)
    upper = np.maximum(raw, modeled)
    if np.any(projected[editable] < lower[editable]) or np.any(
        projected[editable] > upper[editable]
    ):
        row = int(np.flatnonzero(editable & ((projected < lower) | (projected > upper)))[0])
        raise ProcessingError(
            f"coordinate projection row {row}: result left the closed raw/model interval."
        )
    if method == LOWER_ENVELOPE_METHOD and np.any(projected[editable] > raw[editable]):
        row = int(np.flatnonzero(editable & (projected > raw))[0])
        raise ProcessingError(
            f"coordinate projection row {row}: lower-envelope result exceeds raw stress."
        )

    coordinate = _derived_coordinate(strain, projected, modulus)
    for left in np.flatnonzero(active):
        right = int(left) + 1
        if not coordinate[right] > coordinate[left]:
            _raise_pair(
                "projected true-plastic order violation",
                int(left),
                right,
                coordinate[left],
                coordinate[right],
            )
    for left in np.flatnonzero(shape_pair):
        right = int(left) + 1
        if projected[right] < projected[left]:
            _raise_pair(
                "projected engineering-stress shape violation",
                int(left),
                right,
                projected[left],
                projected[right],
            )


def _diagnostics(
    modeled: NDArray[np.float64], projected: NDArray[np.float64]
) -> ProjectionDiagnostics:
    changed = projected != modeled
    rows = np.flatnonzero(changed)
    if not rows.size:
        return ProjectionDiagnostics(0, 0.0, None, None)
    differences = np.abs(projected[rows] - modeled[rows])
    return ProjectionDiagnostics(
        changed_count=int(rows.size),
        max_abs_change=float(np.max(differences)),
        first_affected_row=int(rows[0]),
        last_affected_row=int(rows[-1]),
    )


def _raise_pair(
    kind: str, left: int, right: int, left_value: float, right_value: float
) -> None:
    raise ProcessingError(
        f"coordinate projection rows {left}->{right}: {kind} "
        f"({left_value:.12g} -> {right_value:.12g})."
    )


def _raise_interval(left: int, right: int, lower: float, upper: float) -> None:
    first = max(0, left)
    raise ProcessingError(
        f"coordinate projection rows {first}->{right}: infeasible anchor/shape interval "
        f"[{lower:.12g}, {upper:.12g}]."
    )


__all__ = [
    "DEFAULT_METHOD",
    "LOWER_ENVELOPE_METHOD",
    "METHODS",
    "ProjectionDiagnostics",
    "project_model_stress",
]
