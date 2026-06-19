/-
Difficulty: Easy
Informal statement:
Theorem: Let $\omega$ be the ordinal of natural numbers.
    Consider $F:\omega^{op}\to \mathcal{R}\mathrm{ing}$ with $F_n:=\mathbb{Z}/p^n\mathbb{Z}$ and $f_n:F_{n+1}\to F_n$.
    Then the limit exists.
-/

import Mathlib

open CategoryTheory Limits Opposite

variable (p : ℕ)

noncomputable def pAdicFunctor : ℕᵒᵖ ⥤ RingCat where
  obj n := RingCat.of (ZMod (p ^ (unop n)))
  map {m n} f := RingCat.ofHom <|
    ZMod.castHom (pow_dvd_pow p (leOfHom f.unop)) (ZMod (p ^ (unop n)))
  map_id := by
    intro n
    ext x
    simp
  map_comp := by
    intro x y z f g
    ext x
    simp

theorem pAdic_limit_exists : HasLimit (pAdicFunctor p) := by
  sorry
