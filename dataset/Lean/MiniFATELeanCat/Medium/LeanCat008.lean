/-
Source: LeanCat S_0008
Difficulty: Medium

Informal statement:
Let G and H be groups.

If their binary coproduct exists in the category of groups, then the free
product of G and H is isomorphic to that categorical coproduct.
-/

import Mathlib.GroupTheory.Coprod.Basic
import Mathlib.Algebra.Category.Grp.Basic
import Mathlib.CategoryTheory.Limits.Shapes.BinaryProducts

open CategoryTheory Limits

universe u

variable {G H : GrpCat.{u}}

theorem freeProdGrp_iso_coprod [HasBinaryCoproduct G H] :
    Nonempty (GrpCat.of (Monoid.Coprod G H) ≅ coprod G H) := by
  sorry
  
