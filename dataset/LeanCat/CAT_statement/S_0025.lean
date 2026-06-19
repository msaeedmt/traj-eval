/-
Difficulty: Medium
Informal statement:
Theorem: Let $\mathcal{C}$, $\mathcal{D}$, $\mathcal{E}$ be categories and $U : \mathcal{D}\to \mathcal{C}$, $V : \mathcal{E}\to \mathcal{C}$, $F : \mathcal{D} \to \mathcal{E}$ be functors such that $V \circ F = U$. Suppose $U, V$ have left adjoints and $\mathcal D$ admits coequalizers. If $V$ reflects split epimorphisms to regular epimorphisms, then $F$ has a left adjoint.
-/

import Mathlib

open CategoryTheory

variable {C D E : Type*} [Category C] [Category D] [Category E]

namespace CategoryTheory


class Functor.ReflectsSplitEpimorphismsToRegularEpimorphisms (F : Functor C D) : Prop where
  reflects : ∀ {X Y} {f : X ⟶ Y} [IsSplitEpi (F.map f)], Nonempty (RegularEpi f)

end CategoryTheory

variable (U : D ⥤ C) (V : E ⥤ C) (F : D ⥤ E)


theorem exists_left_adjoint_of_comp_eq (h : F ⋙ V = U) (hU : U.IsRightAdjoint) (hV : V.IsRightAdjoint)
    (hV_refl : V.ReflectsSplitEpimorphismsToRegularEpimorphisms) : F.IsRightAdjoint := by
  sorry
