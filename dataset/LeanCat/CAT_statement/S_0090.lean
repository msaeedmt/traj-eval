/-
Difficulty: Medium
Informal statement:
Definition: A category is called $\textbf{normal}$ if each monomorphism is a kernel.

Definition: A category is called $\textbf{conormal}$ if each epimorphism is a cokernel.

Definition: A category is called $\textbf{binormal}$ if it is both normal and conormal.

Definition: Let $\mathcal C$ be a category.
An object $c\in\mathcal C$ is called $\textbf{mono-simple}$ if it has no proper subobjects.
An object $c\in\mathcal C$ is called $\textbf{epi-simple}$ if it has no proper quotient objects.


Theorem: Let $\mathcal{A}$ be a binormal category.
    Then an object is mono-simple if and only if it is epi-simple.
-/

import Mathlib

open CategoryTheory

variable {A : Type*} [Category A] [Limits.HasZeroMorphisms A]
  [IsNormalMonoCategory A]
  [IsNormalEpiCategory A]

  [Limits.HasKernels A]
  [Limits.HasCokernels A]

theorem binormal_mono_simple_iff_epi_simple (x : A) :
    (∀ (y : A) (f : y ⟶ x) [Mono f], f = 0 ∨ IsIso f) ↔
    (∀ (y : A) (g : x ⟶ y) [Epi g], g = 0 ∨ IsIso g) := by
    sorry
