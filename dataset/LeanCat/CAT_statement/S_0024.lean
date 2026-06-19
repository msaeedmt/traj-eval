/-
Difficulty: Easy
Informal statement:
Theorem: The forgetful functor $U : \mathcal{A}\mathrm{b} \to \mathcal{G}\mathrm{rp}$ admits a left adjoint.
-/

import Mathlib
open CategoryTheory
universe u

theorem forget_CommGrp_to_Grp_admits_left_adjoint :
    (forget₂ CommGrpCat.{u} GrpCat.{u}).IsRightAdjoint := by
  sorry
