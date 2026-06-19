/-
Source: FATE-M 109
Difficulty: Easy
-/

import Mathlib.Algebra.Ring.Basic

theorem fatem_109_mul_left_cancel_of_NoZeroDivisors {R : Type*} [Ring R] [NoZeroDivisors R]
    (a b c : R) (h1 : ¬ a = 0 ∧ a * b = a * c) : b = c := by
  sorry
