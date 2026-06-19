/-
Source: FATE-H 13
Difficulty: Medium
-/

import Mathlib.LinearAlgebra.Matrix.GeneralLinearGroup.Basic
import Mathlib.GroupTheory.Sylow

open Matrix

theorem fateh_013_card_sylow_gl_two_eq_add_one (p : ℕ) [Fact p.Prime] :
    Nat.card (Sylow p <| GL (Fin 2) (ZMod p)) = p + 1 := by
  sorry
