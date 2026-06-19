/-
Source: FATE-M 19
Difficulty: Easy
Informal statement:
For positive integer $n\ge 2$, show that the ring $\mathbb Z/n\mathbb Z$ is a field if and only if
$n$ is a prime number.

-/

import Mathlib.Data.ZMod.Basic
import Mathlib.Algebra.Field.IsField

theorem fatem_019_zmod_isField_iff_prime (n : ℕ) :
    IsField (ZMod n) ↔ Nat.Prime n := by
  sorry
