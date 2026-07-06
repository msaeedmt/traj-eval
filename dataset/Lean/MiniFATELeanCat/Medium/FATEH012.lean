/-
Source: FATE-H 12
Difficulty: Medium

Informal statement:
Prove that the quotient of the special linear group SL two over the finite
field with three elements by its center embeds in the alternating group on
four letters.
-/

import Mathlib.LinearAlgebra.Matrix.SpecialLinearGroup
import Mathlib.GroupTheory.Perm.Sign
import Mathlib.GroupTheory.SpecificGroups.Alternating

open MatrixGroups

theorem fateh_012_exists_sl_quot_center_monoidHom_alternatingGroup :
    ∃ φ : SL(2,ZMod 3) ⧸ Subgroup.center SL(2,ZMod 3) →* alternatingGroup (Fin 4),
      Function.Injective φ := by
  sorry
