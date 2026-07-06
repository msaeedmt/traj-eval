/-
Source: FATE-X 13
Difficulty: Hard

Informal statement:
Let R be a not necessarily commutative ring.

Assume that R is not a field. Also assume that every non-unit x in R
satisfies x squared equals x.

Prove that every x in R satisfies x squared equals x.
-/

import Mathlib.Algebra.Ring.Idempotent
import Mathlib.Algebra.Field.IsField

namespace MiniFATELeanCat.Hard.FATEX013

theorem fatex_013_sq_eq_self_of_not_unit {R : Type} [Ring R] (h : ¬ IsField R)
    (h2 : ∀ x : R, ¬ IsUnit x → x^2 = x) (x : R) :
    x^2 = x := by
  sorry

end MiniFATELeanCat.Hard.FATEX013
