/-
Difficulty: High
Informal statement:
Theorem: There are categories $\mathcal{C}$, $\mathcal{D}$ and $\mathcal{E}$ such that $\mathcal{C}$ is a subcategory of $\mathcal{D}$, $\mathcal{D}$ is a subcategory of $\mathcal{E}$ and $\mathcal{C}$ is reflective in $\mathcal{E}$, but $\mathcal{C}$ is not reflective in $\mathcal{D}$. Here we do not require a reflective subcategory to be full.
-/

import Mathlib

open CategoryTheory Functor

universe u v

namespace CategoryTheory

open Category Adjunction

variable {C : Type u₁} {D : Type u₂} {E : Type u₃}
variable [Category.{v₁} C] [Category.{v₂} D] [Category.{v₃} E]

class Reflective2 (R : D ⥤ C) extends R.Faithful where
  L : C ⥤ D
  adj : L ⊣ R

end CategoryTheory

theorem exists_not_reflective :
    ∃ (E C D : Type u)
    (_ : Category.{v} E) (_ : Category.{v} C) (_ : Category.{v} D) (i : C ⥤ D)
    (_ : Faithful i) (j : D ⥤ E) (_ : Faithful j),
    IsEmpty (Reflective2 i) ∧ Nonempty (Reflective2 (i ⋙ j)) := by
  sorry
