/-
Source: FATE-X 5
Difficulty: Hard
Informal statement:
Let \(p\) be a prime, let \(G\) be a finite p-group. Let A be a maximal normal abelian subgroup
of \(G\). Prove that A is also a maximal abelian subgroup of \(G\).

-/

import Mathlib.GroupTheory.Subgroup.Center
import Mathlib.Data.Fintype.Basic

namespace MiniFATELeanCat.Hard.FATEX005

theorem fatex_005_maximal_abelian_normal_subgroup_of_p_group_is_maximal_abelian_subgroup
    (G : Type) [Group G] [Fintype G] :
    ∃ H : Subgroup G, H ≤ Subgroup.center G ∨ Subgroup.center G ≤ H := by
  sorry

end MiniFATELeanCat.Hard.FATEX005
