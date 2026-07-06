/-
Source: FATE-M 19
Difficulty: Easy

Informal statement:
For every positive integer n at least two, the ring of integers modulo n
is a field if and only if n is prime.
-/

import Mathlib.Data.ZMod.Basic
import Mathlib.Algebra.Field.IsField

theorem fatem_019_zmod_isField_iff_prime (n : ℕ) :
    IsField (ZMod n) ↔ Nat.Prime n := by
  sorry
