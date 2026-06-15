import Mathlib

/--
If $P$ is a $p$-Sylow subgroup of $G$, show that $N(N(P))=N(P)$.
-/
theorem Sylow.normalizer_normalizer_eq_normalizer {G : Type*} [Group G] {p : ℕ} [Fact (Nat.Prime p)]
    [Finite (Sylow p G)] (P : Sylow p G) : Subgroup.normalizer (Subgroup.normalizer (P : Set G) : Set G) = Subgroup.normalizer (P : Set G) := by
  sorry
