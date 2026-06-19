/-
Source: FATE-X 3
Difficulty: Hard
Informal statement:
Let $H$ be a subgroup of finite index of a group $G$. Show that there exists a subset $S$ of $G$,
such that $S$ is both a set of representatives of the left and the right cosets of $H$ in $G$.

-/

import Mathlib.GroupTheory.Complement

namespace MiniFATELeanCat.Hard.FATEX003

theorem fatex_003_exists_leftCoset_rightCoset_representative
    (G : Type) [Group G] (H : Subgroup G) [H.FiniteIndex] :
    ∃ S : Set G, Subgroup.IsComplement S H ∧ Subgroup.IsComplement H S := by
  sorry

end MiniFATELeanCat.Hard.FATEX003
