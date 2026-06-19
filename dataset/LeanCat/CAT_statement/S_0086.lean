/-
Difficulty: Medium
Informal statement:
Theorem: Let $\mathcal{A}$ be an abelian category and let $P\in\mathcal{A}$.
    Then $\hom_{\mathcal{A}}(P,-):\mathcal{A}\to \mathcal{A}\mathrm{b}$ is right exact if and only if $\hom_{\mathcal{A}}(P,-):\mathcal{A}\to \mathcal{A}\mathrm{b}$ preserves epimorphism.
-/

import Mathlib

open CategoryTheory Limits Opposite

variable {A : Type u} [Category.{v} A] [Abelian A]

theorem hom_rightExact_iff_preserves_epi (P : A) :
    PreservesFiniteColimits (preadditiveCoyoneda.obj (op P)) ↔
    Functor.PreservesEpimorphisms (preadditiveCoyoneda.obj (op P)) := by
  sorry
