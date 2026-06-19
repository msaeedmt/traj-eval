/-
Difficulty: Easy
Informal statement:
Theorem: $\mathbb{k}$ is the unique (up to isomorphism) simple object in $\mathrm{Vect}_{\mathbb{k}}$.
-/

import Mathlib

open Module

variable (𝕜 : Type u) [Field 𝕜]

instance isSimpleModule_self : IsSimpleModule 𝕜 𝕜 := by
  infer_instance

theorem unique_simple_object (M : Type v) [AddCommGroup M] [Module 𝕜 M] [IsSimpleModule 𝕜 M] :
    Nonempty (M ≃ₗ[𝕜] 𝕜) := by
  sorry
