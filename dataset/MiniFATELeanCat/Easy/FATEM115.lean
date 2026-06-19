/-
Source: FATE-M 115
Difficulty: Easy
Informal statement:
$R$ is a relation on set $A$, $R^{-1} := \{ (x,y) ~|~ (y,x) \in R\}$,
prove that $R$ is transitive if and only if $R^{-1}$ is transitive.

-/

import Mathlib.Logic.Relation

theorem fatem_115_transitive_iff {A : Type} (R : A → A → Prop) :
    Transitive R ↔ Transitive (fun x y => R y x) := by
  sorry
