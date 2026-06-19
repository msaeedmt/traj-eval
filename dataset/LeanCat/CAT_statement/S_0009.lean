/-
Difficulty: Medium
Informal statement:
Theorem: There exists a morphism in $\mathcal{R}\mathrm{ing}$ such that it is epic but not surjective.\nomenclature{$\mathcal{R}\mathrm{ing}$}{the category of rings}
-/

import Mathlib

open CategoryTheory

theorem exists_epic_not_surjective_in_Ring :
    ∃ (A B : RingCat) (f : A ⟶ B), Epi f ∧ ¬ Function.Surjective f := by
  sorry
