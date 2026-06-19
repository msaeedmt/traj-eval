import Mathlib

/--
Difficulty: Medium (FATE-M)

Let $G$ be a group of order 4. Prove that $G$ must be abelian.
-/
theorem commutative_of_card_eq_four {G : Type*} [Group G] [Fintype G] (h : Fintype.card G = 4) :
    ∀ a b : G, a * b = b * a := by
  sorry
