/-
Source: FATE-H 9
Difficulty: Medium

Informal statement:
Let n be odd and at least three.

In the dihedral group with two n elements, the identity is the only element
that commutes with every element of the group.
-/

import Mathlib.GroupTheory.SpecificGroups.Dihedral

theorem fateh_009_dihedralGroup_centralizer_eq_bot {n : ℕ} (hn : Odd n) (h : n ≥ 3) :
    Subgroup.centralizer ⊤ = (⊥ : Subgroup (DihedralGroup n)) := by
  sorry
