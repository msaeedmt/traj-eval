/-
Difficulty: Medium
Informal statement:
Theorem: Suppose $\mathcal{C}$ is cocomplete and $G :\mathcal{D} \to \mathcal{C}$ is monadic.
    Then $\mathcal{D}$ is cocomplete if and only if $\mathcal{D}$ has coequalizers.
-/

import Mathlib

open CategoryTheory Limits

universe uC uD vC vD w w'

variable {C : Type uC} [Category.{vC} C]
variable {D : Type uD} [Category.{vD} D]
variable (G : D ⥤ C)

theorem cocomplete_iff_hasCoequalizers_of_monadic
  [HasColimitsOfSize.{w, w'} C] [MonadicRightAdjoint G] :
    HasColimitsOfSize.{w, w'} D ↔ HasCoequalizers D := by
  sorry
