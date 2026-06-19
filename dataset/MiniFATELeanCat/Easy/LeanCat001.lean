/-
Source: LeanCat S_0001
Difficulty: Easy
-/

import Mathlib.CategoryTheory.Functor.Basic
import Mathlib.CategoryTheory.Functor.Category
import Mathlib.CategoryTheory.NatTrans

open CategoryTheory

variable {C : Type*} [Category.{v} C]

theorem leancat_s0001_id_comm (alpha beta : (Functor.id C) ⟶ (Functor.id C)) :
    alpha ≫ beta = beta ≫ alpha := by
  sorry
