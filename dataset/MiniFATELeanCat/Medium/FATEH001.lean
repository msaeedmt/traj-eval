/-
Source: FATE-H 1
Difficulty: Medium
-/

import Mathlib.GroupTheory.FiniteIndexNormalSubgroup

theorem fateh_001_subgroup_normal_index_le_factorial {G : Type} [Group G] {n : ℕ} (hn : n ≠ 0)
    (H : Subgroup G) (hH : H.index = n) :
    ∃ K : Subgroup G, K.Normal ∧ K ≤ H ∧ K.index ≠ 0 ∧ K.index ≤ n.factorial := by
  sorry
