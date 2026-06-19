/-
Source: FATE-M 109
Difficulty: Easy

Informal statement:
Let R be an integral domain.

If a is nonzero and a times b equals a times c, then b equals c.
-/

import Mathlib.Algebra.Ring.Basic

theorem fatem_109_mul_left_cancel_of_NoZeroDivisors {R :Type*} [Ring R] [NoZeroDivisors R]
    (a b c : R) (h₁ : ¬ a = 0 ∧ a * b = a * c) : b = c := by
  sorry
