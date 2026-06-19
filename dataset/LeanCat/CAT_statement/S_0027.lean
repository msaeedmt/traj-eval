/-
Difficulty: Medium
Informal statement:
Theorem: Let $(\mathbb{Z},\leq)$ be a poset, regarded as a category, then $f\in \mathrm{End}(\mathbb{Z})$ has left adjoint if and only if it has a right adjoint.
-/

import Mathlib

open CategoryTheory

theorem int_endofunctor_hasLeftAdjoint_iff_hasRightAdjoint (f : ℤ ⥤ ℤ) :
    f.IsRightAdjoint ↔ f.IsLeftAdjoint := by
  sorry
