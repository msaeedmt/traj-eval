/-
Difficulty: Medium
Informal statement:
Theorem: Let $\mathcal{D}$ be a small-complete locally small category, a functor $ G : \mathcal{D}\to  \mathcal{C}$ has a left adjoint if and only if $G$ is continuous and for each $c\in \mathcal{C}$, the comma category $(c\downarrow G)$ admits an initial object.
-/

import Mathlib

open CategoryTheory Limits

variable {D : Type u} [Category.{v} D] [HasLimits D] [LocallySmall.{v} D]
variable {C : Type u} [Category.{v} C]
variable (G : D ⥤ C)

theorem has_left_adjoint_iff_continuous_and_initials :
    G.IsRightAdjoint ↔ PreservesLimits G ∧ ∀ (c : C), HasInitial (StructuredArrow c G) := by
  sorry
