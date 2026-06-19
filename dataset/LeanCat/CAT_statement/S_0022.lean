/-
Difficulty: Medium
Informal statement:
Theorem: Let $\mathcal{C}$ and $\mathcal{D}$ be locally small categories and let $F:\mathcal{C}\to \mathcal{D}$ be a functor.
    Then $F$ admits a right adjoint if and only if for each $d\in\mathcal{D}$, $\hom_{\mathcal{D}}(F(-),d):\mathcal{C}^{op}\to\mathcal{S}\mathrm{et}$ is representable.
-/

import Mathlib

open CategoryTheory

variable {C : Type u₁} [Category.{v} C] {D : Type u₂} [Category.{v} D]

theorem isLeftAdjoint_iff_yoneda_comp_op_isRepresentable (F : C ⥤ D) :
    F.IsLeftAdjoint ↔ ∀ (d : D), (F.op ⋙ yoneda.obj d).IsRepresentable := by
  sorry
