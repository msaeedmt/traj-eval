import Mathlib

/--
Difficulty: Medium (FATE-M)

Let $G$ be a group, and $a, b, c \in G$.
Prove that the equation $a x c=b$ has a unique solution in $G$.
-/
theorem existUnique_mul_eq {G : Type*} [Group G] (a b c : G) : ∃! x : G, a * x * b = c := by
  sorry
