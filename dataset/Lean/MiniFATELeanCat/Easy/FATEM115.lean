/-
Source: FATE-M 115
Difficulty: Easy

Informal statement:
Let R be a relation on a set A, and let the inverse relation contain the
pairs whose reversed pairs belong to R.

Then R is transitive if and only if its inverse relation is transitive.
-/

import Mathlib.Logic.Relation

theorem fatem_115_transitive_iff {A : Type} (R : A → A → Prop) :
    (Transitive R) ↔ (Transitive (fun x y => R y x)) := by
  sorry
