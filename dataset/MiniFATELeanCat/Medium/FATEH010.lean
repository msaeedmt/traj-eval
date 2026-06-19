/-
Source: FATE-H 10
Difficulty: Medium
Informal statement:
Prove that the last two digits of $3^{3^{100}} is 03.

-/

import Mathlib.Data.Nat.ModEq

theorem fateh_010_three_pow_three_pow_mod_100 : 3 ^ (3 ^ 100) % 100 = 3 := by
  sorry
