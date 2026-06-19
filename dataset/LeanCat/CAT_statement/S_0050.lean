/-
Difficulty: Medium
Informal statement:
Definition: Let $\mathcal C$ be a locally small category.
An object $c \in\mathcal C$ is called $\textbf{compact}$ if $\mathrm{hom}_{\mathcal C} (c,-)$ preserves filtered colimits.


Theorem: For $\mathcal{S}\mathrm{et}$, an object is compact if and only if it is a finite set.
-/

import Mathlib

open CategoryTheory Limits

theorem isCompactObject_iff_finite_type (X : Type u) :
    PreservesFilteredColimits (coyoneda.obj (Opposite.op X)) ↔ Finite X := by
  sorry
