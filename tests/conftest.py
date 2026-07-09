"""Shared fixtures."""

import pytest

from tiresias.models.dataset import dataset_from_labeled
from tiresias.models.train_baseline import train_and_evaluate
from tiresias.synth.generate import generate_dataset


@pytest.fixture(scope="session")
def trained_model():
    """A small RF model trained once per test session for downstream tests."""
    df = dataset_from_labeled(generate_dataset(sessions_per_class=8, seed=5))
    tm = train_and_evaluate(df, model_type="rf", seed=1, with_latency=False)
    return tm.model
