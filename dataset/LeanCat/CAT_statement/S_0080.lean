/-
Difficulty: Easy
Informal statement:
Theorem: Let $\mathcal{A}$ be an abelian category and let $f$ be a morphism in $\mathcal{A}$.
    Then $f$ is an isomorphism if and only if $f$ is monic and epic.
-/

import Mathlib

open CategoryTheory

variable {C : Type*} [Category C] [Abelian C]

theorem isIso_iff_mono_and_epi {X Y : C} (f : X ⟶ Y) :
    IsIso f ↔ (Mono f ∧ Epi f) := by
  sorry
