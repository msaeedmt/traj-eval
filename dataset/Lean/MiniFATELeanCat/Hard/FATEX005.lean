/-
Source: FATE-X 5
Difficulty: Hard

Informal statement:
Let p be prime, and let G be a finite p-group.

Let A be a maximal normal abelian subgroup of G. Prove that A is also a
maximal abelian subgroup of G.
-/

import Mathlib.GroupTheory.PGroup
import Mathlib.GroupTheory.Subgroup.Center

namespace MiniFATELeanCat.Hard.FATEX005

theorem fatex_005_maximal_abelian_normal_subgroup_of_p_group_is_maximal_abelian_subgroup
    (p : ℕ) (hp : p.Prime) (G : Type) [Group G] [Finite G] (h_pgroup : IsPGroup p G)
    (H : Subgroup G) (h_normal : H.Normal) (h_comm : IsMulCommutative H)
    (h_maximal_normal_abelian :
      ∀ (K : Subgroup G), K.Normal → IsMulCommutative K → H ≤ K → H = K) :
    ∀ (K : Subgroup G), IsMulCommutative K → H ≤ K → H = K := by
  sorry

end MiniFATELeanCat.Hard.FATEX005
