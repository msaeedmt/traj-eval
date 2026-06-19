import Mathlib

/--
Difficulty: Medium (FATE-M)

In any ring $R$ and $a,b,c\in R$, $a(b-c)=a b-a c$ and $(b-c) a=b a-c a$.
-/
theorem mul_sub_and_sub_mul {R : Type*} [Ring R] (a b c : R) :
    a * (b - c) = a * b - a * c ∧ (b - c) * a = b * a - c * a := by
  sorry
