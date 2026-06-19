/-
Difficulty: Medium
Informal statement:
Theorem: View the poset $\mathbb{N} = (\mathbb{N},\leq)$ of natural numbers as a category. There is a sequence of distinct functors $G_n:\mathbb{N}\to \mathbb{N}$ such that $G_0(x)=x+1$ and $G_{n+1}\dashv G_n$ for each $n\in \mathbb{N}$.
-/

import Mathlib

open CategoryTheory

theorem exists_sequence_of_distinct_adjoints_nat :
    ∃ G : ℕ → (ℕ ⥤ ℕ),
      Function.Injective G ∧
      (∀ x, (G 0).obj x = x + 1) ∧
      (∀ n, Nonempty (G (n + 1) ⊣ G n)) := by
  sorry
