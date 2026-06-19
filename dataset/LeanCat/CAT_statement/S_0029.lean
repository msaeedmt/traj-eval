/-
Difficulty: Medium
Informal statement:
Theorem: Let $(-)^{\times}: \mathcal{R}\mathrm{ing} \to \mathcal{G}\mathrm{rp}$ mapping a ring to its group of units. Then it admits a left adjoint.
-/

import Mathlib

open CategoryTheory

def RingCat.units : RingCat.{u} ⥤ GrpCat.{u} where
  obj R := .of Rˣ
  map f := GrpCat.ofHom (Units.map f.hom)

theorem exists_leftAdjoint_unitFunctor :
    ∃ (left : GrpCat.{u} ⥤ RingCat.{u}), Nonempty (left ⊣ RingCat.units.{u}) := by
    sorry
