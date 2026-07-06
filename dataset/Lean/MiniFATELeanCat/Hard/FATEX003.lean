/-
Source: FATE-X 3
Difficulty: Hard

Informal statement:
Let H be a subgroup of finite index in a group G.

Show that there is a subset S of G that is both a set of representatives
for the left cosets of H and a set of representatives for the right cosets
of H.
-/

import Mathlib.GroupTheory.Complement

namespace MiniFATELeanCat.Hard.FATEX003

theorem fatex_003_exists_leftCoset_rightCoset_representative
    (G : Type) [Group G] (H : Subgroup G) [H.FiniteIndex] :
    ∃ S : Set G, Subgroup.IsComplement S H ∧ Subgroup.IsComplement H S := by
  sorry

end MiniFATELeanCat.Hard.FATEX003
