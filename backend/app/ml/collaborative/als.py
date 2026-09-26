"""
Implicit-feedback Alternating Least Squares (ALS) matrix factorization.

Pure-numpy implementation of the model from Hu, Koren & Volinsky (2008),
"Collaborative Filtering for Implicit Feedback Datasets". It learns two
separate low-rank factor matrices:

    user_factors : (n_users, f)
    item_factors : (n_items, f)

A collaborative score for (user u, item i) is the dot product
`user_factors[u] . item_factors[i]`. These factors are learned ONLY from the
user-item interaction matrix; they are NOT content embeddings and must never be
substituted for them.

This is intentionally dependency-light (numpy only) so it trains inside the
existing worker without adding a compiled dependency. For very large catalogs
the `implicit` library is a drop-in replacement with the same factor semantics;
see docs/RECOMMENDATION_ARCHITECTURE.md.
"""

from __future__ import annotations

import numpy as np


class ALSModel:
    """Weighted-regularization implicit ALS (Hu et al. 2008)."""

    def __init__(
        self,
        factors: int = 64,
        regularization: float = 0.05,
        alpha: float = 40.0,
        iterations: int = 15,
        seed: int = 42,
    ) -> None:
        if factors <= 0:
            raise ValueError("factors must be a positive integer")
        self.factors = int(factors)
        self.regularization = float(regularization)
        self.alpha = float(alpha)
        self.iterations = int(iterations)
        self.seed = int(seed)

        self.user_factors: np.ndarray | None = None
        self.item_factors: np.ndarray | None = None

    def fit(self, interactions: np.ndarray) -> "ALSModel":
        """
        Train on a dense (n_users, n_items) matrix of non-negative interaction
        weights `r_ui`. Confidence is `c_ui = 1 + alpha * r_ui`; preference is
        `p_ui = 1` where `r_ui > 0` else `0`.
        """
        R = np.asarray(interactions, dtype=np.float64)
        if R.ndim != 2:
            raise ValueError("interactions must be a 2D matrix")
        n_users, n_items = R.shape
        f = self.factors

        rng = np.random.default_rng(self.seed)
        X = 0.01 * rng.standard_normal((n_users, f))
        Y = 0.01 * rng.standard_normal((n_items, f))

        # Confidence and preference (Hu et al. 2008)
        C = 1.0 + self.alpha * R
        P = (R > 0.0).astype(np.float64)
        lambda_eye = self.regularization * np.eye(f)

        for _ in range(self.iterations):
            X = self._solve_side(Y, C, P, lambda_eye)          # update users
            Y = self._solve_side(X, C.T, P.T, lambda_eye)      # update items

        self.user_factors = X
        self.item_factors = Y
        return self

    @staticmethod
    def _solve_side(
        fixed: np.ndarray,
        C: np.ndarray,
        P: np.ndarray,
        lambda_eye: np.ndarray,
    ) -> np.ndarray:
        """
        Solve one side of the ALS update given the fixed factor matrix.

        For each row r: solve (F^T C_r F + lambda I) x = F^T C_r p_r, using the
        identity  F^T C_r F = F^T F + F^T (C_r - I) F  which avoids materializing
        the full diagonal confidence matrix.
        """
        FtF = fixed.T @ fixed
        n_rows = C.shape[0]
        f = fixed.shape[1]
        out = np.zeros((n_rows, f), dtype=np.float64)

        for r in range(n_rows):
            Cr = C[r]                     # (n_fixed,)
            Cr_minus = Cr - 1.0
            # F^T (C_r - I) F
            FtCrF = fixed.T @ (Cr_minus[:, None] * fixed)
            A = FtF + FtCrF + lambda_eye
            b = fixed.T @ (Cr * P[r])
            out[r] = np.linalg.solve(A, b)
        return out

    def recommend(
        self,
        user_index: int,
        n: int = 20,
        exclude_item_indices: set[int] | None = None,
    ) -> list[tuple[int, float]]:
        """Return top-n (item_index, score) for a trained user index."""
        if self.user_factors is None or self.item_factors is None:
            raise RuntimeError("ALSModel is not trained")
        scores = self.item_factors @ self.user_factors[user_index]
        exclude = exclude_item_indices or set()
        order = np.argsort(-scores)
        results: list[tuple[int, float]] = []
        for idx in order:
            i = int(idx)
            if i in exclude:
                continue
            results.append((i, float(scores[i])))
            if len(results) >= n:
                break
        return results

    def score(self, user_index: int, item_index: int) -> float:
        """Collaborative dot-product score for a (user, item) pair."""
        if self.user_factors is None or self.item_factors is None:
            raise RuntimeError("ALSModel is not trained")
        return float(self.user_factors[user_index] @ self.item_factors[item_index])
