/-
Source: FATE-X 3
Difficulty: Hard
-/

import Mathlib.GroupTheory.Complement

namespace MiniFATELeanCat.Hard.FATEX003

theorem fatex_003_exists_leftCoset_rightCoset_representative
    (G : Type) [Group G] (H : Subgroup G) [H.FiniteIndex] :
    ∃ S : Set G, Subgroup.IsComplement S H ∧ Subgroup.IsComplement H S := by
  sorry

end MiniFATELeanCat.Hard.FATEX003
