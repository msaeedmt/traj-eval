/-
Difficulty: High
Informal statement:
Definition: Let $(\mathcal C,U)$ be a concrete category over $\mathcal B$.
A morphism $f: x\to y$ in $\mathcal C$ is called $\textbf{initial}$ if for any object $c\in \mathcal C$, a morphism $g:U(c)\to U(x)$ is a morphism in $\mathcal{C}$ whenever $f\circ g: U(c)\to U(y)$ is a morphism in $\mathcal C$.

Definition: An initial morphism $f:x\to y$ such that the underlying morphism $U(f):U(x)\to U(y)$ is monic is called an $\textbf{embedding}$.

Definition: If $f:x\to y$ is an embedding, then $(x, f)$ is called an $\textbf{initial subobject}$ of $y$.

Definition: In a concrete category an object $I$ is called $\textbf{injective}$ provided that for any embedding $m: A \to B$ and any morphism $f: A\to C$ there exists a morphism $g:B\to C$ extending $f$, i.e., $g\circ m=f$


Definition: A concrete category $\textbf{has enough injectives}$ provided that each of its objects is an initial subobject of an injective object.

Theorem: The category $\mathcal{T}\mathrm{op}^{CH}$ of compact Hausdorff space has enough injectives.
-/

import Mathlib

open CategoryTheory

namespace CAT_statement_S_0011

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


def HasEnoughInj {C : ConcreteCat (X:= X)} : Prop :=
  ∀ x: C.C, ∃ (I : C.C) (f : x ⟶ I),
    IsInjectiveObj I ∧  IsEmbedding f

end AHS

def CompHausConcrete : AHS.ConcreteCat (X := Type u) :=
{ C := CompHaus.{u}
  U := forget CompHaus}

theorem CompHaus_Has_EnoughInj :AHS.HasEnoughInj (C:= CompHausConcrete) := by
  sorry

end CAT_statement_S_0011
