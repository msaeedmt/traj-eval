/-
Difficulty: High
Informal statement:
Definition: A category $\mathcal C$ is called $\textbf{concretizable}$ over a category $\mathcal B$ if there exists a faithful functor $U:\mathcal C\to \mathcal B$.


Theorem: There exist categories that are not concretizable over $\mathcal{S}\mathrm{et}$.
-/

import Mathlib

open CategoryTheory

theorem exists_category_not_concretizable_over_Type :
    ∃ (C : Type u) (_ : Category.{v} C), ¬ ∃ (F : C ⥤ Type v), F.Faithful := by
  sorry
