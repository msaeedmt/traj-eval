/-
Source: LeanCat S_0001
Difficulty: Easy
Informal statement:
Theorem: Let $\mathcal{C}$ be a category and $\mathrm{Id}_{\mathcal{C}}$ the identity functor. Then monoid of natural transformations $\mathrm{End}(\mathrm{Id}_{\mathcal{C}})$ is commutative.

-/

import Mathlib.CategoryTheory.Functor.Basic
import Mathlib.CategoryTheory.Functor.Category
import Mathlib.CategoryTheory.NatTrans

open CategoryTheory

variable {C : Type*} [Category.{v} C]

theorem leancat_s0001_id_comm (alpha beta : (Functor.id C) ⟶ (Functor.id C)) :
    alpha ≫ beta = beta ≫ alpha := by
  sorry
