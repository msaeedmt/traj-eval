/-
Difficulty: Medium
Informal statement:
Theorem: A functor that reflects equalizers (or finite products) reflects isomorphisms.
-/

import Mathlib

open CategoryTheory Limits


variable {C : Type u} [Category.{v} C] {D : Type u'} [Category.{v'} D]

theorem reflectsIsomorphisms_of_reflects_equalizers (F : C ⥤ D)
    [ReflectsLimitsOfShape WalkingParallelPair F] : F.ReflectsIsomorphisms := by
  sorry

theorem reflectsIsomorphisms_of_reflects_finite_products (F : C ⥤ D)
    [ReflectsLimitsOfShape (Discrete PEmpty) F] [ReflectsLimitsOfShape (Discrete WalkingPair) F] :
    F.ReflectsIsomorphisms := by
  sorry
