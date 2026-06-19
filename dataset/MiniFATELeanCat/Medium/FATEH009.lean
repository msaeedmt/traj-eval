/-
Source: FATE-H 9
Difficulty: Medium
-/

import Mathlib.GroupTheory.SpecificGroups.Dihedral

theorem fateh_009_dihedralGroup_centralizer_eq_bot {n : ℕ} (hn : Odd n) (h : n ≥ 3) :
    Subgroup.centralizer ⊤ = (⊥ : Subgroup (DihedralGroup n)) := by
  sorry
