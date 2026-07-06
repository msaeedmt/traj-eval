/-
Source: LeanCat S_0041
Difficulty: Hard

Informal statement:
Let C be a concrete category over a base category B.

A universal arrow over an object x of B is a morphism from x to the
underlying object of some object c of C, satisfying the usual universal
property.

A free object over x is an object c of C equipped with such a universal
arrow.

In the non-full subcategory of complete lattices whose morphisms preserve
meets and joins, there exists a free object over a set X if and only if X
has at most two elements.
-/

import Mathlib.CategoryTheory.ConcreteCategory.Forget
import Mathlib.Order.Category.CompleteLat
import Mathlib.SetTheory.Cardinal.Basic

open CategoryTheory

universe u v w

namespace MiniFATELeanCat.Hard.LeanCat041

structure FreeObject {C : Type u} [Category.{v} C]
    {FC : C → C → Type*} {CC : C → Type w}
    [∀ X Y, FunLike (FC X Y) (CC X) (CC Y)] [ConcreteCategory.{w} C FC]
    (x : Type w) where
  (obj : C)
  (emb : x ⟶ (forget C).obj obj)
  (uniq : ∀ (Y : C) (f : x ⟶ (forget C).obj Y), ∃! (g : obj ⟶ Y), emb ≫ (forget C).map g = f)


theorem leancat_s0041_complete_lattice_category (X : Type u) :
    Nonempty (FreeObject (C := CompleteLat) X) ↔ Cardinal.mk X ≤ 2 := by
  sorry

end MiniFATELeanCat.Hard.LeanCat041
