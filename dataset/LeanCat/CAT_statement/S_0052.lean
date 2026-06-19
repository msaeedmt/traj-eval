/-
Difficulty: Medium
Informal statement:
Theorem: Let $X,Y,Z$ be objects in $\mathcal{S}\mathrm{et}$ with morphisms $f:X\to Z$ and $g:Y\to Z$.
    Then $\{(x,y)\in X\times Y\mid f(x)=g(y)\}$ is the pullback $X\times_Z Y$ of $X$ and $Y$ over $Z$.
-/

import Mathlib

open CategoryTheory Limits Functor Types Function Pullback

theorem Function.isPullback_pulllback {X Y Z : Type u} (f : X → Z) (g : Y → Z) :
    IsPullback (C := Type u)
      (TypeCat.ofHom (fst (f := f) (g := g)))
      (TypeCat.ofHom (snd (f := f) (g := g)))
      (TypeCat.ofHom f)
      (TypeCat.ofHom g) := by
  sorry
