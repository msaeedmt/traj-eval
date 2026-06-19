/-
Difficulty: High
Informal statement:
Definition: Let $\mathcal C$ be a category and let $c\in \mathcal C$ be an object.
A $\textbf{regular subobject}$ of $c$ is a pair $(x,i)$ where $i$ is a regular monomorphism.

Definition: Let $\mathcal C$ be a category.
$\mathcal C$ is called $\textbf{regular wellpowered}$ if no object in $\mathcal C$ has a proper class of pairwise non-isomorphic regular subobjects.

Definition: A category $\mathcal C$ is called $\textbf{concretizable}$ over a category $\mathcal B$ if there exists a faithful functor $U:\mathcal C\to \mathcal B$.


Theorem: Let $\mathcal{C}$ be a category that admits finite limits.
    Then $\mathcal{C}$ is concretizable over $\mathcal{S}\mathrm{et}$ if and only if $\mathcal{C}$ is regular wellpowered.
-/

import Mathlib

namespace CAT_statement_S_0038

open CategoryTheory Limits

universe u v w

variable {C : Type u} [Category C] [HasFiniteLimits C]

def IsConcretizable (X : Type v) [Category X] (D: Type u) [Category D] : Prop :=
  ∃ (U : D ⥤ X), U.Faithful

variable (C)

class RegularWellPowered : Prop where
  regularSubobject_small : ∀ (X : C), Small.{v} { P : Subobject X //  Nonempty (RegularMono P.arrow) }

theorem concretizable_iff_regular_wellpowered :
    IsConcretizable (Type u) C ↔ RegularWellPowered C := by
  sorry

end CAT_statement_S_0038
