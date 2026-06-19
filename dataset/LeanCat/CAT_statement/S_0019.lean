/-
Difficulty: Easy
Informal statement:
Theorem: A functor $G : \mathcal{D} \to \mathcal{C}$ has a left adjoint if and only if for each $c \in\mathcal{C}$, the comma category $(c \downarrow G)$ has an initial object.
-/

import Mathlib

open CategoryTheory Limits

variable {C : Type*} {D : Type*} [Category.{v₁} C] [Category.{v₂} D]

theorem functor_hasLeftAdjoint_iff_structuredArrow_hasInitial
    (G : D ⥤ C) :
    G.IsRightAdjoint ↔ ∀ c : C, HasInitial (StructuredArrow c G) := by
  sorry
