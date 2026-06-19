/-
Source: FATE-X 5
Difficulty: Hard
-/

import Mathlib.GroupTheory.Subgroup.Center
import Mathlib.Data.Fintype.Basic

namespace MiniFATELeanCat.Hard.FATEX005

theorem fatex_005_maximal_abelian_normal_subgroup_of_p_group_is_maximal_abelian_subgroup
    (G : Type) [Group G] [Fintype G] :
    ∃ H : Subgroup G, H ≤ Subgroup.center G ∨ Subgroup.center G ≤ H := by
  sorry

end MiniFATELeanCat.Hard.FATEX005
