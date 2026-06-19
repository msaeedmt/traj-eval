/-
Source: FATE-M 41
Difficulty: Easy

Informal statement:
Let g be the pair consisting of a in G and b in H.

If a has order m and b has order n, then g has order equal to the least
common multiple of m and n.
-/

import Mathlib.GroupTheory.OrderOfElement

theorem fatem_041_orderOf_prod {G H : Type*} [Group G] [Group H] {a : G} {b : H} :
    orderOf (a, b) = Nat.lcm (orderOf a) (orderOf b) := by
  sorry
