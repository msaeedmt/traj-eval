/-
Difficulty: High
Informal statement:
Definition: For $F : \mathcal{C} \to \mathcal{D}$, we define the induced cocontinuous functor $\mathrm{Lan}_{F^{op}} : \mathcal{P}sh(\mathcal{C}) \to \mathcal{P}sh(\mathcal{D})$, by $\phi\mapsto \phi \star yF$, where $\phi\star yF$ is the $\phi$-weighted colimit of the diagram $yF$ and $y$ is the Yoneda embedding.

Notation: $\mathrm{Sind}(\mathcal{C})$ := free cocompletion of $\mathcal{C}$ under small sifted colimits;

Theorem: For any full and faithful $I : \mathcal{C} \to \mathcal D$ between small categories, $\phi\in [\mathcal C ^{op}, \mathcal Set]$ is in $\mathrm{Sind}(\mathcal C)$ iff $\mathrm{Lan}_{I^{op}}$ is in $\mathrm{Sind}(\mathcal D)$.

Reference: Lemma 6.2, Chen Ruiyuan 2021, On sifted colimits in the presence of pullbacks, arXiv:2109.12708
-/

import Mathlib

namespace CAT_statement_S_0078

open CategoryTheory Limits Functor

universe u v

namespace CategoryTheory

namespace Limits

variable {C : Type u} [Category.{v} C]


structure SindObjectPresentation (A : Cᵒᵖ ⥤ Type v) where
  I : Type v
  [ℐ : SmallCategory I]
  [hI : IsSifted I]
  F : I ⥤ C
  ι : F ⋙ yoneda ⟶ (Functor.const I).obj A
  isColimit : IsColimit (Cocone.mk A ι)


structure IsSindObject (A : Cᵒᵖ ⥤ Type v) : Prop where
  mk' :: nonempty_presentation : Nonempty (SindObjectPresentation A)

theorem IsSindObject.mk {A : Cᵒᵖ ⥤ Type v} (P : SindObjectPresentation A) : IsSindObject A :=
  ⟨⟨P⟩⟩

end Limits

namespace Functor

axiom weightedColimitFunctor {J : Type v} [SmallCategory J] {E : Type u} [Category.{v} E]
    (W : Jᵒᵖ ⥤ Type v) (G : J ⥤ E) : E ⥤ Type v


abbrev WeightedColimitData {J : Type v} [SmallCategory J] {E : Type u} [Category.{v} E]
    (W : Jᵒᵖ ⥤ Type v) (G : J ⥤ E) (colim : E) :=
  (weightedColimitFunctor W G).CorepresentableBy colim


abbrev HasWeightedColimit {J : Type v} [SmallCategory J] {E : Type u} [Category.{v} E]
    (W : Jᵒᵖ ⥤ Type v) (G : J ⥤ E) :=
  (weightedColimitFunctor W G).IsCorepresentable


noncomputable def weightedColimit {J : Type v} [SmallCategory J] {E : Type u} [Category.{v} E]
    (W : Jᵒᵖ ⥤ Type v) (G : J ⥤ E) [h : HasWeightedColimit W G] : E :=
  h.has_corepresentation.choose

noncomputable def weightedColimitData {J : Type v} [SmallCategory J] {E : Type u} [Category.{v} E]
    (W : Jᵒᵖ ⥤ Type v) (G : J ⥤ E) [h : HasWeightedColimit W G] :
    WeightedColimitData W G (weightedColimit W G) :=
  h.has_corepresentation.choose_spec.some

end Functor

end CategoryTheory

open CategoryTheory Limits Functor

variable {C D : Type u} [SmallCategory C] [SmallCategory D]

def lanDiagram (F : C ⥤ D) : C ⥤ (Dᵒᵖ ⥤ Type u) := F ⋙ yoneda


noncomputable def lanPresheaf (F : C ⥤ D) (φ : Cᵒᵖ ⥤ Type u)
    [HasWeightedColimit φ (lanDiagram F)] : Dᵒᵖ ⥤ Type u :=
  weightedColimit φ (lanDiagram F)


theorem isSindObject_iff_isSindObject_lanPresheaf
    (I : C ⥤ D) [Full I] [Faithful I] (φ : Cᵒᵖ ⥤ Type u)
    [HasWeightedColimit φ (lanDiagram I)] :
    IsSindObject φ ↔ IsSindObject (lanPresheaf I φ) := by
  sorry

end CAT_statement_S_0078
