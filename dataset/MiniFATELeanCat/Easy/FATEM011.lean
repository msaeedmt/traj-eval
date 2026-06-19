/-
Source: FATE-M 11
Difficulty: Easy
Informal statement:
In any ring $R$ and $a,b,c\in R$, $a(b-c)=a b-a c$ and $(b-c) a=b a-c a$.

-/

import Mathlib.Algebra.Ring.Basic

theorem fatem_011_mul_sub_and_sub_mul {R : Type*} [Ring R] (a b c : R) :
    a * (b - c) = a * b - a * c ∧ (b - c) * a = b * a - c * a := by
  sorry
