import Mathlib

open CategoryTheory

universe u v w

namespace CAT_statement_S_0041

axiom FreeObject {C : Type u} [Category.{v} C] (x : Type w) : Type (max u v w)


theorem complete_lattice_category (X : Type u) :
    Nonempty (FreeObject (C := CompleteLat) X) ↔ Cardinal.mk X ≤ 2 := by
    sorry

end CAT_statement_S_0041
