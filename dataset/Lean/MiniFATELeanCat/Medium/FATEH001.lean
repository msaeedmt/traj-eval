/-
Source: FATE-H 1
Difficulty: Medium

Informal statement:
Let H be a subgroup of G with index n.

Prove that there is a normal subgroup K of G contained in H such that the
index of K in G is at most n factorial.
-/

import Mathlib.GroupTheory.FiniteIndexNormalSubgroup

theorem fateh_001_subgroup_normal_index_le_factorial {G : Type} [Group G] {n : ℕ} (hn : n ≠ 0)
    (H : Subgroup G) (hH : H.index = n) :
    ∃ K : Subgroup G, K.Normal ∧ K ≤ H ∧ K.index ≠ 0 ∧ K.index ≤ n.factorial := by
  sorry
