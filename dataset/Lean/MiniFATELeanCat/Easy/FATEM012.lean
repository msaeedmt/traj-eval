/-
Source: FATE-M 12
Difficulty: Easy

Informal statement:
Let R be a ring with unit.

There is a unique ring homomorphism from the integers to R that sends one
to the multiplicative identity of R.
-/

import Mathlib.Algebra.Ring.Basic
import Mathlib.Algebra.Ring.Hom.Defs
import Mathlib.Algebra.Ring.Int.Defs
import Mathlib.Data.Int.Basic

theorem fatem_012_existUnique_ringHom_int {R : Type*} [Ring R] :
    ∃! f : ℤ →+* R, True := by
  sorry
