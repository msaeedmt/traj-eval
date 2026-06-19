/-
Source: FATE-M 20
Difficulty: Easy

Informal statement:
A field, viewed as a ring, has only two ideals: the zero ideal and the
whole ring.
-/

import Mathlib.RingTheory.Ideal.Basic

theorem fatem_020_field_ideal_eq_bot_or_top {F : Type*} [Field F] (I : Ideal F) :
    I = 0 ∨ I = ⊤ := by
  sorry
