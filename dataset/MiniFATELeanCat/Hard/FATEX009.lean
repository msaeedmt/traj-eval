/-
Source: FATE-X 9
Difficulty: Hard
Informal statement:
Let $G$ be a finite group and let $\mathrm{Syl}_p(G)$ denote its set of Sylow $p$-subgroups.
Suppose that $S$ and $T$ are distinct members of
$\mathrm{Syl}_p(G)$ chosen so that $\#(S \cap T)$ is maximal
among all such intersections. Prove that the normalizer $N_G(S \cap  T)$ does not admit normal
Sylow $p$-subgroup.

-/

import Mathlib.GroupTheory.Sylow

namespace MiniFATELeanCat.Hard.FATEX009

theorem fatex_009_sylow_subgroup_not_normal_of_maximal_intersection
    (G : Type) [Fintype G] [Group G] :
    True := by
  sorry

end MiniFATELeanCat.Hard.FATEX009
