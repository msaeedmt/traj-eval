/-
Difficulty: Easy
Informal statement:
Theorem: Let $\mathcal{C}$ be a category and let $f,g$ be morphisms in $\mathcal{C}$ such that $f\circ g$ is monic. Then $g$ is monic.
-/

import Mathlib

open CategoryTheory

variable {C : Type*} [Category C]


theorem monic_of_comp_monic {X Y Z : C} (g : X ⟶ Y) (f : Y ⟶ Z)
    [Mono (g ≫ f)] : Mono g := by
  sorry
