/-
Source: FATE-X 13
Difficulty: Hard
Informal statement:
Let $(R,+,\cdot)$ be a (not necessarily commutative) ring.
If we know that $R$ is not a field and $x^2=x$ for any $x\in R,$
where $x$ is not invertible. Prove that $x^2=x$ for any $x.$

-/

import Mathlib.Algebra.Ring.Idempotent
import Mathlib.Algebra.Field.IsField

namespace MiniFATELeanCat.Hard.FATEX013

theorem fatex_013_sq_eq_self_of_not_unit {R : Type} [Ring R] (h : ¬ IsField R) :
    ∃ x : R, x ^ 2 = x := by
  sorry

end MiniFATELeanCat.Hard.FATEX013
