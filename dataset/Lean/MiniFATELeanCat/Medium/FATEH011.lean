/-
Source: FATE-H 11
Difficulty: Medium

Informal statement:
Let G be a group of order 3825.

If H is a normal subgroup of G with order 17, then H is contained in the
center of G.
-/

import Mathlib.GroupTheory.Subgroup.Center
import Mathlib.SetTheory.Cardinal.Finite

theorem fateh_011_le_center_of_card_eq_17_of_card_eq_3825 {G : Type} [Group G]
    (h : Nat.card G = 3825) (H : Subgroup G) [H.Normal] (hH : Nat.card H = 17) :
    H ≤ Subgroup.center G := by
  sorry
