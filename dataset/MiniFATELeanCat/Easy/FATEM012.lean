/-
Source: FATE-M 12
Difficulty: Easy
Informal statement:
Let $R$ be a ring with unit. Then there is a unique homomorphism
$f:\mathbb Z\to R$ such that $1\mapsto 1_R$.

-/

import Mathlib.Algebra.Ring.Basic
import Mathlib.Algebra.Ring.Hom.Defs
import Mathlib.Algebra.Ring.Int.Defs
import Mathlib.Data.Int.Basic

theorem fatem_012_existUnique_ringHom_int {R : Type*} [Ring R] :
    ∃! f : ℤ →+* R, True := by
  sorry
