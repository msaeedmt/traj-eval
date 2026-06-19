/-
Source: FATE-M 111
Difficulty: Easy
Informal statement:
If $a^{2}=0$ in $R$, show that $a x+x a$ commutes with $a$.

-/

import Mathlib.Algebra.Ring.Commute

theorem fatem_111_commute_of_pow_two_zero (R : Type) [Ring R] (a : R) (h : a ^ 2 = 0) :
    ∀ x : R, Commute (a * x + x * a) a := by
  sorry
