/-
Difficulty: Easy
Informal statement:
Theorem: Let $\mathcal{C}$ and $\mathcal{E}$ be two categories and let $F:\mathcal{C}\to \mathcal{E}$ be a functor.
    Let $\bullet $ be the terminal category consisting of a unique object $\bullet$ and a unique morphism.
    Then a colimit of $F$ is a left Kan extension of $F$ along $K:\mathcal{C}\to \bullet$, i.e. $\mathrm{Lan}_KF(\bullet)=\mathrm{colim} F$.
-/

import Mathlib

open CategoryTheory Limits

universe u₁ v₁ u₂ v₂

variable {C : Type u₁} [Category.{v₁} C]
variable {E : Type u₂} [Category.{v₂} E]


theorem colimit_is_leftKanExtension_along_to_terminal
    (F : C ⥤ E) (K : C ⥤ PUnit) [HasColimit F] [K.HasLeftKanExtension F] :
    Nonempty ((K.leftKanExtension F).obj PUnit.unit ≅ colimit F) := by
  sorry
