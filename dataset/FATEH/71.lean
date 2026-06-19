import Mathlib

open Polynomial

/--
Difficulty: Hard (FATE-H)

Prove that $k[x,y]$ is not a Dedekind ring.
-/
theorem not_isDedekindRing_mvPolynomial_fin_two {k : Type} [Field k] :
    ¬ IsDedekindRing (MvPolynomial (Fin 2) k) := by
  sorry
