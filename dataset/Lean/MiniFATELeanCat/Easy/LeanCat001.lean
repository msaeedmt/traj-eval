/-
Source: LeanCat S_0001
Difficulty: Easy

Informal statement:
Let C be a category, and let the identity functor on C be given.

The monoid of natural transformations from the identity functor to itself
is commutative.
-/

import Mathlib.CategoryTheory.Functor.Basic
import Mathlib.CategoryTheory.Functor.Category
import Mathlib.CategoryTheory.NatTrans

open CategoryTheory

variable {C : Type*} [Category.{v} C]

theorem leancat_s0001_id_comm (α β : (𝟭 C) ⟶ (𝟭 C)) :
    α ≫ β = β ≫ α := by
  sorry
