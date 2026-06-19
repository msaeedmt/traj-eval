/-
Difficulty: High
Informal statement:
Definition: Let $\mathcal C$ be a locally small category.
An object $c \in\mathcal C$ is called $\textbf{compact}$ if $\mathrm{hom}_{\mathcal C} (x,-)$ preserves filtered colimits.


Theorem: For $\mathcal{G}\mathrm{rp}$, an object is compact if and only if it is finitely presented as a group. Every group can be realized as a direct limit of finitely presented groups.
-/

import Mathlib

open CategoryTheory

namespace CAT_statement_S_0063

universe u

def IsFinitelyPresentedGrp (X : Type u) [Group X] : Prop :=
    ∃ (α : Type u) (rels : Set (FreeGroup α)), Finite α ∧ rels.Finite ∧ Nonempty (X ≃* PresentedGroup rels)

theorem isCompactObject_Grp_iff_finite_presented (X : Type u) [Group X] :
    CategoryTheory.IsFinitelyPresentable (GrpCat.of X) ↔ IsFinitelyPresentedGrp X := by
  sorry


theorem group_realized_as_direct_limit_of_finitely_presented_groups (X : Type u) [Group X] :
    ∃ (J : Type u) (inst₁ : CategoryTheory.SmallCategory J) (inst₂ : CategoryTheory.IsFiltered J) (F : CategoryTheory.Functor J GrpCat), ∀ (j : J), IsFinitelyPresentedGrp (F.obj j) ∧ Nonempty (X ≃* GrpCat.FilteredColimits.colimit F) := by
    sorry

end CAT_statement_S_0063
