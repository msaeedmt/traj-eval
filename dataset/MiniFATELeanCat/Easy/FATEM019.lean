/-
Source: FATE-M 19
Difficulty: Easy
-/

import Mathlib.Data.ZMod.Basic
import Mathlib.Algebra.Field.IsField

theorem fatem_019_zmod_isField_iff_prime (n : ℕ) :
    IsField (ZMod n) ↔ Nat.Prime n := by
  sorry
