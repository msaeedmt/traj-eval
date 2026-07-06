/-
Source: FATE-M 111
Difficulty: Easy

Informal statement:
Let R be a ring.

If a squared is zero in R, then a times x plus x times a commutes with a.
-/

import Mathlib.Algebra.Ring.Commute

theorem fatem_111_commute_of_pow_two_zero (R : Type) [Ring R] (a : R) (h : a ^ 2 = 0) :
    ∀ x : R, Commute (a * x + x * a) a := by
  sorry
