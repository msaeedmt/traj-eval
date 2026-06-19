/-
Difficulty: Medium
Informal statement:
Theorem: Let $\mathcal{C}$ be a category.
    Then $\mathcal{C}$ admits all small limits if and only if $\mathcal{C}$ admits all small products and pullbacks.
-/

import Mathlib

open CategoryTheory Limits

variable {C : Type u} [Category.{v} C]

theorem has_limits_iff_has_products_and_pullbacks :
    HasLimitsOfSize.{v, v} C ↔ (∀ (J : Type v), HasLimitsOfShape (Discrete J) C) ∧ HasLimitsOfShape WalkingCospan C := by
  sorry
