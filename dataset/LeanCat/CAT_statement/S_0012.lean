/-
Difficulty: High
Informal statement:
Theorem: Let $\mathcal{C}$ be a category and let $f:x\to y$ be a morphism in $\mathcal{C}$.
    Then $f$ is a monomorphism in $\mathcal{C}$ if and only if there exists a category $\mathcal{D}$ and a faithful functor $I:\mathcal{C}\to\mathcal{D}$ such that $f$ is a section in $\mathcal{D}$.
-/

import Mathlib

open CategoryTheory Functor


theorem mono_iff_exists_embedding_section
  {C : Type u} [Category.{v} C] {X Y : C} (f : X ⟶ Y) :
    Mono f ↔ ∃ (D : Type (max u v)) (_ : Category.{v} D) (I : C ⥤ D) (_ : Faithful I),
    IsSplitMono (I.map f) := by
  sorry
