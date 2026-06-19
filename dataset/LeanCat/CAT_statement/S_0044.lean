/-
Difficulty: Easy
Informal statement:
Theorem: Filtered colimits commute with finite limits in $\mathcal{S}\mathrm{et}$.
-/

import Mathlib

open CategoryTheory Limits

variable {J : Type u} [SmallCategory J] [FinCategory J]
variable {K : Type u} [SmallCategory K] [IsFiltered K]
variable (F : J ⥤ K ⥤ Type u)


theorem filteredColimitsCommuteWithFiniteLimits :
  Nonempty (colimit (limit F) ≅ limit (colimit F.flip)) := by
  sorry
