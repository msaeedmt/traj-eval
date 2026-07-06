/-
Source: FATE-M 11
Difficulty: Easy

Informal statement:
In any ring R and for any elements a, b, and c in R, left multiplication
and right multiplication distribute over subtraction.

In other words, a times b minus c equals a times b minus a times c, and
b minus c times a equals b times a minus c times a.
-/

import Mathlib.Algebra.Ring.Basic

theorem fatem_011_mul_sub_and_sub_mul {R : Type*} [Ring R] (a b c : R) :
    a * (b - c) = a * b - a * c ∧ (b - c) * a = b * a - c * a := by
  sorry
