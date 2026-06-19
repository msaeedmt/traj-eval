/-
Difficulty: Easy
Informal statement:
Theorem: Let $\mathcal{C}$ and $\mathcal{D}$ be categories and let $F:\mathcal{C}\to \mathcal{D}$ be a functor that admits a right adjoint $G$.
    Then $F$ is fully faithful if and only if $u:\mathrm{Id}_{\mathcal{C}}\to G\circ F$ is isomorphism.
-/

import Mathlib

open CategoryTheory

variable {C D : Type*} [Category C] [Category D] (F : C ⥤ D) (G : D ⥤ C)

theorem fully_faithful_iff_unit_isIso (adj : F ⊣ G) :
    (F.Full ∧ F.Faithful) ↔ IsIso adj.unit := by
  sorry
