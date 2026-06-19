/-
Source: FATE-M 115
Difficulty: Easy
-/

import Mathlib.Logic.Relation

theorem fatem_115_transitive_iff {A : Type} (R : A → A → Prop) :
    Transitive R ↔ Transitive (fun x y => R y x) := by
  sorry
