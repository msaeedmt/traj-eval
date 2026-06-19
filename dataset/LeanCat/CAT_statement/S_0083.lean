/-
Difficulty: Medium
Informal statement:
Theorem: $\mathbb{Z}_p$ is simple object in $\mathcal{A}\mathrm{b}$ when $p$ is prime number.
-/

import Mathlib

open CategoryTheory

variable (p : ℕ) [Fact p.Prime]

theorem ZMod_simple : CategoryTheory.Simple (ModuleCat.of ℤ (ZMod p)) := by
  sorry
