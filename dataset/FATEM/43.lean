import Mathlib

/--
Difficulty: Medium (FATE-M)

In a ring with unity, prove that if $a$ is nilpotent, then $a+1$ and $a-1$ are both invertible.
-/
theorem invertible_of_nilpotent {R : Type*} [Ring  R] (a : R) (h : IsNilpotent a) :
    IsUnit (1 + a) ∧ IsUnit (1 - a) := by
  sorry
