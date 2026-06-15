import Mathlib

open CategoryTheory Limits Functor Types Function Pullback

theorem Function.isPullback_pulllback {X Y Z : Type u} (f : X → Z) (g : Y → Z) :
    IsPullback (C := Type u)
      (TypeCat.ofHom (fst (f := f) (g := g)))
      (TypeCat.ofHom (snd (f := f) (g := g)))
      (TypeCat.ofHom f)
      (TypeCat.ofHom g) := by
  sorry
