import Mathlib

open CategoryTheory Topology

universe u v w uX vX

variable {X : Type uX} [Category.{vX} X]

namespace CAT_statement_S_0039

structure ConcreteCat (X : Type uX) [Category.{vX} X] where
  C : Type u
  [cat : Category.{vX} C]
  U : C ⥤ X
  [U_Faithful : U.Faithful]

attribute [instance] ConcreteCat.cat ConcreteCat.U_Faithful


def IsConcreteFunc {A B : ConcreteCat (X := X)} (F : A.C ⥤ B.C) : Prop :=
  Nonempty ((F ⋙ B.U) ≅ A.U)

axiom forgetFrm : Frm.{u} ⥤ Type u

axiom forgetFrm_faithful : forgetFrm.Faithful

instance : forgetFrm.Faithful := forgetFrm_faithful


structure T0TopCat where
  toTop : TopCat.{u}
  is_t0 : T0Space (↑toTop)

namespace T0TopCat

instance : CoeSort T0TopCat (Type u) := ⟨fun X => X.toTop⟩
instance (X : T0TopCat) : TopologicalSpace X := X.toTop.str
attribute [instance] T0TopCat.is_t0


axiom category : Category.{u} T0TopCat

attribute [instance] category


axiom forget_0 : T0TopCat ⥤ TopCat


axiom forget_0_faithful : forget_0.Faithful

instance : forget_0.Faithful := forget_0_faithful


@[simp] def of (X : Type u) [TopologicalSpace X] [T0Space X] : T0TopCat :=
  ⟨TopCat.of X, inferInstance⟩


axiom L : T0TopCatᵒᵖ ⥤ Type u

axiom L_faithful : L.Faithful

instance : L.Faithful := L_faithful

end T0TopCat


noncomputable def FrmConcrete : ConcreteCat (X := Type u) :=
{ C := Frm.{u}
  U := (forgetFrm) }

noncomputable def T0TopCatopConcrete : ConcreteCat (X := Type u) :=
{ C := T0TopCatᵒᵖ
  U := (T0TopCat.L) }

def ConcreteFuncsIso (A B : ConcreteCat (X := Type u)) : Type _ :=
  { F : A.C ⥤ B.C // IsConcreteFunc (A := A) (B := B) F }

theorem unique_concrete_functors_from_T0TopCatop_to_Frm_iso :
    Nat.card (ConcreteFuncsIso T0TopCatopConcrete FrmConcrete) = 1 := by
  sorry

end CAT_statement_S_0039
