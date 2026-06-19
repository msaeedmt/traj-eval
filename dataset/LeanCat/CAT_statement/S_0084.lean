/-
Difficulty: Medium
Informal statement:
Theorem: $\mathcal{G}\mathrm{rp}$ is not an additive category.
-/

import Mathlib

open CategoryTheory Limits


def IsAdditiveCategory (C : Type u) [Category.{v} C] : Prop :=
  ∃ (_ : Preadditive C), HasZeroObject C ∧ HasFiniteBiproducts C

theorem Grp_not_is_additive : IsEmpty (IsAdditiveCategory GrpCat.{u}) := by
  sorry
