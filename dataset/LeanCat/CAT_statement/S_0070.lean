/-
Difficulty: High
Informal statement:
Definition: A concrete category $(\mathcal C, U)$ over $\mathcal B$ is said to $\textbf{have (small) concrete limits}$ if $\mathcal C$ has all small limits and $U$ preserves them.


Theorem: Let $(\mathcal{C},U)$ have small concrete limits.
    Then $U$ reflects small limits if and only if $U$ reflects isomorphisms.
-/

import Mathlib

open CategoryTheory Limits

variable {C : Type u} [Category.{v} C]
variable {D : Type u'} [Category.{v'} D]
variable (U : C ⥤ D)


theorem reflects_limits_iff_reflects_isomorphisms_preserves_limits
    [HasLimitsOfSize.{v, v} C]
    [PreservesLimitsOfSize.{v, v} U]
    [CategoryTheory.Functor.Faithful U]
:
    ReflectsLimitsOfSize.{v, v} U ↔ U.ReflectsIsomorphisms := by
  sorry
