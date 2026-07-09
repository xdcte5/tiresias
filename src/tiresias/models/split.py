"""Session-based train/test splitting.

Flows from the same session are correlated (same app instance, same server, adjacent
in time). Splitting flows randomly would leak that correlation across train/test and
inflate the score. We always split on ``session_id`` so every session lands wholly in
train or wholly in test.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold, GroupShuffleSplit

from .dataset import SESSION_COL


@dataclass
class SplitIndices:
    train: np.ndarray
    test: np.ndarray


def session_train_test_split(
    df: pd.DataFrame, test_size: float = 0.25, seed: int = 42
) -> SplitIndices:
    """One grouped split. Guarantees no session appears in both train and test."""
    groups = df[SESSION_COL].to_numpy()
    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train_idx, test_idx = next(gss.split(df, groups=groups))
    return SplitIndices(train=train_idx, test=test_idx)


def session_folds(df: pd.DataFrame, n_splits: int = 5):
    """Yield grouped CV folds (train_idx, test_idx) for cross-validated reporting."""
    groups = df[SESSION_COL].to_numpy()
    n_groups = len(np.unique(groups))
    gkf = GroupKFold(n_splits=min(n_splits, n_groups))
    yield from gkf.split(df, groups=groups)


def sessions_disjoint(df: pd.DataFrame, split: SplitIndices) -> bool:
    """True iff no session id is shared between the train and test index sets."""
    train_sessions = set(df.iloc[split.train][SESSION_COL])
    test_sessions = set(df.iloc[split.test][SESSION_COL])
    return train_sessions.isdisjoint(test_sessions)
