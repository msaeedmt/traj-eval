/-
Difficulty: High
Informal statement:
Definition: An Abelian category $\mathcal A$ is called $\textbf{semisimple}$ if any short exact sequence in $\mathcal A$ is splittable.


Theorem: Let $\mathcal{A}$ be an abelian category.
    Then the followings are equivalent:
    \begin{enumerate}
        \item $\mathcal{A}$ is semisimple;
        \item any obejct in $\mathcal{A}$ is injective;
        \item any object in $\mathcal{A}$ is projective.
    \end{enumerate}
-/

import Mathlib

open CategoryTheory Limits

variable {A : Type u} [Category.{v} A] [Abelian A]

def IsSemisimple (A : Type u) [Category.{v} A] [Abelian A] : Prop :=
  ∀ (S : ShortComplex A), S.ShortExact → Nonempty S.Splitting

theorem isSemisimple_iff_injective_iff_projective :
    (IsSemisimple A ↔ ∀ (X : A), Injective X) ∧
    (IsSemisimple A ↔ ∀ (X : A), Projective X) := by
  sorry
