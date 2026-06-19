/-
Source: FATE-H 97
Difficulty: Medium

Informal statement:
Prove that the sine of one degree is algebraic over the rational numbers.
-/

import Mathlib.Analysis.SpecialFunctions.Trigonometric.Basic
import Mathlib.RingTheory.Algebraic.Defs

open Real

theorem fateh_097_isAlgebraic_sin_pi_div_180 :
    IsAlgebraic ℚ (sin (π / 180)) := by
  sorry
