/-
Source: FATE-H 12
Difficulty: Medium
Informal statement:
Prove that \( SL_2(\mathbb{F}_3) / Z(SL_2(\mathbb{F}_3)) \le A_4 \).

-/

import Mathlib.LinearAlgebra.Matrix.SpecialLinearGroup
import Mathlib.GroupTheory.Perm.Sign
import Mathlib.GroupTheory.SpecificGroups.Alternating

open MatrixGroups

theorem fateh_012_exists_sl_quot_center_monoidHom_alternatingGroup :
    ∃ phi : SL(2, ZMod 3) ⧸ Subgroup.center SL(2, ZMod 3) →* alternatingGroup (Fin 4),
      Function.Injective phi := by
  sorry
