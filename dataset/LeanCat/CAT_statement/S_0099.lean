/-
Difficulty: Medium
Informal statement:
Theorem: The monad associated with the forgetful functor $\mathcal{T}\mathrm{op}\to \mathcal{S}\mathrm{et}$ is idempotent.
-/

import Mathlib

open CategoryTheory

theorem monad_Top_idempotent : IsIso TopCat.adj₁.toMonad.μ := by
  sorry
