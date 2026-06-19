import Mathlib

open ComplexConjugate

/--
Difficulty: Medium (FATE-M)

Prove that the set of complex numbers fixed conjugation is the set of real numbers
-/
theorem conj_fixedPoint_eq : {z : ℂ | conj z = z} = {z : ℂ | ∃ (x : ℝ), z = x} := by
  sorry
