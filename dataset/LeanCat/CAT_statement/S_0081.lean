/-
Difficulty: Easy
Informal statement:
Theorem: Let $\mathcal{A}$ be an abelian category and let $f$ be a morphism in $\mathcal{A}$.
    Then $f$ is monic if and only if $\ker(f)=0$.
-/

import Mathlib

open CategoryTheory Limits Category

variable {C : Type*} [Category C] [Abelian C]

theorem mono_iff_isZero_kernel {X Y : C} (f : X ⟶ Y) :
    Mono f ↔ IsZero (kernel f) := by
  sorry
