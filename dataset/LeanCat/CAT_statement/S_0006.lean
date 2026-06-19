/-
Difficulty: Medium
Informal statement:
Theorem: Let $\mathcal{C}$ and $\mathcal{D}$ be two categories.
    Let $F:\mathcal{C}\to\mathcal{D}$ be a functor.
    Then $F$ has a quasi-inverse if and only if
    \begin{enumerate}
        \item $F$ is fully faithful;
        \item $F$ is essentially surjective.
    \end{enumerate}
-/

import Mathlib

open CategoryTheory


theorem funtor_has_quasi_inverse_iff {C D : Type*} [Category C] [Category D] (F : C ⥤ D):
    (∃ G : D ⥤ C, (Nonempty (Functor.id C ≅ F.comp G)) ∧ (Nonempty (G.comp F ≅ Functor.id D)))
    ↔ F.IsEquivalence := by
 sorry
