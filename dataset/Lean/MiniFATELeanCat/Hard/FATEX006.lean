/-
Source: FATE-X 6
Difficulty: Hard

Informal statement:
Prove that a group with exactly 396 elements is not simple.
-/

import Mathlib.GroupTheory.Subgroup.Simple
import Mathlib.SetTheory.Cardinal.Finite

namespace MiniFATELeanCat.Hard.FATEX006

theorem fatex_006_not_isSimpleGroup_of_card_eq_396 (G : Type) [Group G]
    [Finite G] (h_card : Nat.card G = 396) : ¬ IsSimpleGroup G := by
  sorry

end MiniFATELeanCat.Hard.FATEX006
