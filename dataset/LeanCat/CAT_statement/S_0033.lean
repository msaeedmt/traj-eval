/-
Difficulty: High
Informal statement:
Theorem: $\mathcal{T}\mathrm{op}^{CH}$ has precisely two full, isomorphism-closed, coreflective subcategories.
-/

import Mathlib

open CategoryTheory Topology

namespace CAT_statement_S_0033

structure FullCoreflectiveSubcategory (C : Type u) [Category.{v} C] where
  obj : ObjectProperty C
  iso_closed : obj.IsClosedUnderIsomorphisms
  coreflective : Coreflective obj.ι

theorem CompHaus_has_precisely_two_coreflective_subcategories :
    Nat.card (FullCoreflectiveSubcategory CompHaus) = 2 := by
  sorry

end CAT_statement_S_0033
