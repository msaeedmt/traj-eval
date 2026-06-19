/-
Difficulty: Easy
Informal statement:
Theorem: For any monad $(T,\mu,\eta)$ on a category $\mathcal{C}$ and let $\mathcal{C}^T$ be its Elienberg-Moore category.
    Let $U:\mathcal{C}^T\to\mathcal{C}$ be the forgetful functor, then it admits a left adjoint.
-/

import Mathlib

open CategoryTheory

variable {C : Type u₁} [Category.{v₁} C]


theorem monad_forget_has_left_adjoint (T : Monad C) :
    T.forget.IsRightAdjoint := by
  sorry
