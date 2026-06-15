import Mathlib

open CategoryTheory

def RingCat.units : RingCat.{u} ⥤ GrpCat.{u} where
  obj R := .of Rˣ
  map f := GrpCat.ofHom (Units.map f.hom)

theorem exists_leftAdjoint_unitFunctor :
    ∃ (left : GrpCat.{u} ⥤ RingCat.{u}), Nonempty (left ⊣ RingCat.units.{u}) := by
    sorry
