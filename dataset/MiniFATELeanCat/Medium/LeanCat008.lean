/-
Source: LeanCat S_0008
Difficulty: Medium
Informal statement:
Theorem: Let $G$ and $H$ be groups, and let $K$ be another group. For any group
homomorphisms $f : G \to K$ and $g : H \to K$, there exists a group homomorphism
from the coproduct/free product of $G$ and $H$ to $K$.

-/

import Mathlib.GroupTheory.Coprod.Basic

variable {G H K : Type*} [Group G] [Group H] [Group K]

theorem leancat_s0008_freeProdGrp_universal (f : G →* K) (g : H →* K) :
    Nonempty (Monoid.Coprod G H →* K) := by
  sorry
