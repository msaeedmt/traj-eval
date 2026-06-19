/-
Difficulty: Medium
Informal statement:
Theorem: The forgetful functor $\mathcal{T}\mathrm{op}\to\mathcal{S}\mathrm{et}$, $\mathcal{G}\mathrm{rp}\to\mathcal{S}\mathrm{et}$, $\mathcal{R}\mathrm{ing}\to\mathcal{A}\mathrm{b}$, $\mathcal{T}\mathrm{op}_*\to\mathcal{T}\mathrm{op}$ are faithful but not full.\nomenclature{$\mathcal{S}\mathrm{et}$}{the category of sets}\nomenclature{$\mathcal{A}\mathrm{b}$}{the category of abelian groups}\nomenclature{$\mathcal{T}\mathrm{op}_*$}{the category of topological spaces with a based point}\nomenclature{$\mathcal{T}\mathrm{op}$}{the category of topological spaces}
-/

import Mathlib

open CategoryTheory Limits


theorem forget_Top_faithful_not_full :
    (forget TopCat).Faithful ∧ ¬ (forget TopCat).Full := by
  sorry


theorem forget_Grp_faithful_not_full :
    (forget GrpCat).Faithful ∧ ¬ (forget GrpCat).Full := by
  sorry


theorem forget_Ring_Ab_faithful_not_full :
    (forget₂ RingCat Ab).Faithful ∧ ¬ (forget₂ RingCat Ab).Full := by
  sorry


theorem forget_TopPointed_faithful_not_full :
    (Under.forget (terminal TopCat)).Faithful ∧ ¬ (Under.forget (terminal TopCat)).Full := by
  sorry
