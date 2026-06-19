/-
Source: LeanCat S_0041
Difficulty: Hard
-/

import Mathlib.Order.Category.CompleteLat
import Mathlib.SetTheory.Cardinal.Basic

open CategoryTheory

universe u v w

namespace MiniFATELeanCat.Hard.LeanCat041

axiom FreeObject {C : Type u} [Category.{v} C] (x : Type w) : Type (max u v w)

theorem leancat_s0041_complete_lattice_category (X : Type u) :
    Nonempty (FreeObject (C := CompleteLat) X) ↔ Cardinal.mk X ≤ 2 := by
  sorry

end MiniFATELeanCat.Hard.LeanCat041
