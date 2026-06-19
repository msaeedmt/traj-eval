/-
Source: FATE-H 97
Difficulty: Medium
Informal statement:
Prove that $\sin 1^{\circ}$ is algebraic over $\mathbb{Q}$.

-/

import Mathlib.Analysis.SpecialFunctions.Trigonometric.Basic
import Mathlib.RingTheory.Algebraic.Defs

theorem fateh_097_isAlgebraic_sin_pi_div_180 :
    IsAlgebraic ℚ (Real.sin (Real.pi / 180)) := by
  sorry
