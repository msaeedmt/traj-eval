import Mathlib

open CategoryTheory

namespace CAT_statement_S_0015

universe u uX vX

variable {X : Type uX} [Category.{vX} X]

namespace AHS

structure ConcreteCat (X : Type uX) [Category.{vX} X] where
  C : Type u
  [cat : Category.{vX} C]
  U : C ⥤ X
  [U_Faithful : U.Faithful]

attribute [instance] ConcreteCat.cat ConcreteCat.U_Faithful


def IsInitialHom {C : ConcreteCat (X:= X)} {A B : C.C} (f : A ⟶ B) : Prop :=
  ∀ ⦃Z : C.C⦄ (g : C.U.obj Z ⟶ C.U.obj A),
    (∃ h : Z ⟶ B, C.U.map h = g ≫ C.U.map f) →
      (∃ k : Z ⟶ A, C.U.map k = g)


def IsEmbedding {C : ConcreteCat (X:= X)} {A B : C.C} (f : A ⟶ B) : Prop :=
  IsInitialHom f ∧ Mono (C.U.map f)


def IsInjectiveObj {C : ConcreteCat (X:= X)} (I : C.C) : Prop :=
  ∀ ⦃A B : C.C⦄ (m : A ⟶ B),
    IsEmbedding  m →
    ∀ (f : A ⟶ I), ∃ g : B ⟶ I, m ≫ g = f

end AHS

namespace SemilatInfCat

axiom forget : SemilatInfCat.{u} ⥤ Type u

axiom forget_faithful : forget.Faithful

instance : forget.Faithful := forget_faithful

noncomputable def SemilatInfCatConcrete : AHS.ConcreteCat (X := Type u) :=
{ C := SemilatInfCat.{u}
  U := forget }


class IsFrameObj (P : SemilatInfCat.{u}) (sSup : Set P.X → P.X) (sInf : Set P.X → P.X): Prop where
  exists_sSup :
      (∀ (s : Set P.X), IsLUB s (sSup s))
  exists_sInf :
      (∀ (s : Set P.X), IsGLB s (sInf s))
  distributive :
      (∀ (a : P.X), ∀ (s : Set P.X),
        a ⊓ sSup s = sSup (Set.image (fun (b : P.X) => a ⊓ b) s))


theorem AHS_injective_iff_frameObj (P : SemilatInfCat) :
    AHS.IsInjectiveObj (C := SemilatInfCatConcrete) P ↔ ∃ (sSup : Set P.X → P.X) (sInf : Set P.X → P.X), IsFrameObj P sSup sInf := by
  sorry

end SemilatInfCat

end CAT_statement_S_0015
