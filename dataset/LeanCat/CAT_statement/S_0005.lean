/-
Difficulty: Easy
Informal statement:
Theorem: Let $\mathcal{C}$ be a category, if every idempotent in $\mathcal{C}$ can be factored into an epimorhisms followed by a monomorphism, then all idempotents split in $\mathcal{C}$.
-/

import Mathlib

open CategoryTheory Idempotents

variable {C : Type*} [Category.{v} C]

theorem idempotent_splitting_from_epi_mono_factorization
    (h : ∀ (X : C) (p : X ⟶ X) (hpp : p ≫ p = p),
      ∃ (Y : C) (e : X ⟶ Y) (he : Epi e) (m : Y ⟶ X) (hm : Mono m), p = e ≫ m) :
    IsIdempotentComplete C := by
  sorry
