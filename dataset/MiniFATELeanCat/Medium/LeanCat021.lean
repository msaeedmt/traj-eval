/-
Source: LeanCat S_0021
Difficulty: Medium
-/

import Mathlib.CategoryTheory.Adjunction.Basic

open CategoryTheory

variable {C : Type u1} [Category.{v1} C] {D : Type u2} [Category.{v2} D]

theorem leancat_s0021_right_adjoint_isEquivalence_iff_left_full_faithful_and_right_conservative
    (F : C ⥤ D) (G : D ⥤ C) (adj : F ⊣ G) :
    G.IsEquivalence ↔ (F.Full ∧ F.Faithful) ∧ G.ReflectsIsomorphisms := by
  sorry
