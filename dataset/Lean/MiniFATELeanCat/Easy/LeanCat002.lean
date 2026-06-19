/-
Source: LeanCat S_0002
Difficulty: Easy

Informal statement:
Let C be a category, and let f and g be morphisms in C.

If the composite f after g is monic, then g is monic.
-/

import Mathlib.CategoryTheory.Category.Basic

open CategoryTheory

variable {C : Type*} [Category C]

theorem leancat_s0002_monic_of_comp_monic {X Y Z : C} (g : X ⟶ Y) (f : Y ⟶ Z)
    [Mono (g ≫ f)] : Mono g := by
  sorry
