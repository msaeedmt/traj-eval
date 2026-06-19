/-
Source: LeanCat S_0008
Difficulty: Medium
-/

import Mathlib.GroupTheory.Coprod.Basic

variable {G H K : Type*} [Group G] [Group H] [Group K]

theorem leancat_s0008_freeProdGrp_universal (f : G →* K) (g : H →* K) :
    Nonempty (Monoid.Coprod G H →* K) := by
  sorry
