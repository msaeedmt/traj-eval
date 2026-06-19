/-
Difficulty: Medium
Informal statement:
Theorem: Let $\mathcal{C}$, $\mathcal{D}$ be categories and $F : \mathcal{C}\to \mathcal{D}$ be a left adjoint functor to $G: \mathcal{D} \to \mathcal{C}$.
    Denote the induced monad of the adjunction $F \dashv G$ by $T := GF$.
    Let $K : \mathcal{D} \to \mathcal{C}^T$ be the comparison functor.
    If $\mathcal{D}$ admits coequalizers, then $K$ has a left adjoint.
-/

import Mathlib

open CategoryTheory Monad

universe u₁ u₂ v₁

variable {C : Type u₁} [Category.{v₁} C] {D : Type u₂} [Category.{v₁} D]
variable (F : C ⥤ D) (G : D ⥤ C) (adj : F ⊣ G)

theorem comparison_adjunction
    [∀ (A : adj.toMonad.Algebra), Limits.HasCoequalizer (F.map A.a) (adj.counit.app (F.obj A.A))] :
    ∃ K : adj.toMonad.Algebra ⥤ D, Nonempty (K ⊣ comparison adj) := by
    sorry
