/-
Difficulty: Medium
Informal statement:
Theorem: Let $\mathcal{B}$ be a complete category.
    Then $\mathcal{B}$ has an initial object if and only if there exists a small set $I$ and an $I$-indexed family of objects $x_i$ such that, for every $s\in \mathcal{B}$, there is an $i\in I$ and an arrow $x_i \to s$.
-/

import Mathlib

open CategoryTheory Limits

variable {B : Type u} [Category.{v} B]

theorem hasInitial_iff_exists_weakly_initial [HasLimits B] :
    HasInitial B ↔ ∃ (I : Type v) (x : I → B), ∀ (s : B), ∃ (i : I), Nonempty (x i ⟶ s) := by
  sorry
