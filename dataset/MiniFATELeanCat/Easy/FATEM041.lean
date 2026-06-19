/-
Source: FATE-M 41
Difficulty: Easy
-/

import Mathlib.GroupTheory.OrderOfElement

theorem fatem_041_orderOf_prod {G H : Type*} [Group G] [Group H] {a : G} {b : H} :
    orderOf (a, b) = Nat.lcm (orderOf a) (orderOf b) := by
  sorry
