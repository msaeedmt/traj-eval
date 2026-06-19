/-
Source: LeanCat S_0008
Difficulty: Medium
Informal statement:
Theorem: Let $G_1$ and $G_2$ be two objects in the category $\mathcal{G}\mathrm{rp}$ of groups.
The coproduct of $G_1$ and $G_2$ in $\mathcal{G}\mathrm{rp}$ is equivalent to the free product of $G_1$ and $G_2$.

-/

import Mathlib.GroupTheory.Coprod.Basic

variable {G H K : Type*} [Group G] [Group H] [Group K]

theorem leancat_s0008_freeProdGrp_universal (f : G →* K) (g : H →* K) :
    Nonempty (Monoid.Coprod G H →* K) := by
  sorry
