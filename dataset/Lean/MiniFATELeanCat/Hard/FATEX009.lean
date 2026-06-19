/-
Source: FATE-X 9
Difficulty: Hard

Informal statement:
Let G be a finite group, and let the Sylow p-subgroups of G be given.

Suppose S and T are distinct Sylow p-subgroups chosen so that the size of
their intersection is maximal among all intersections of distinct Sylow
p-subgroups.

Prove that the normalizer of the intersection of S and T has no normal
Sylow p-subgroup.
-/

import Mathlib.GroupTheory.Sylow

namespace MiniFATELeanCat.Hard.FATEX009

theorem fatex_009_sylow_subgroup_not_normal_of_maximal_intersection
    (G : Type) [Finite G] [Group G] (p : ℕ) [Fact (Nat.Prime p)] (S T : Sylow p G)
    (h_ne : S ≠ T)
    (h_maximal : ∀ (S' T' : Sylow p G), S' ≠ T' →
      ((S' : Set G) ⊓ T').ncard ≤ ((S : Set G) ⊓ T).ncard) :
    ∀ (P : Sylow p (Subgroup.normalizer (((S : Subgroup G) ⊓ T : Subgroup G) : Set G))),
      ¬ P.Normal := by
  sorry

end MiniFATELeanCat.Hard.FATEX009
