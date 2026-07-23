from __future__ import annotations

import torch

from doc_inspector.config import AppSettings
from doc_inspector.retrieval import memory_efficient_maxsim, retrieval_metrics


def test_colqwen_model_is_switchable_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("COLQWEN_MODEL", "local-test-model")

    assert AppSettings(_env_file=None).colqwen_model == "local-test-model"


def test_memory_efficient_maxsim_matches_reference_tensor() -> None:
    queries = [
        torch.tensor([[1.0, 0.0], [0.0, 1.0]]),
        torch.tensor([[1.0, 1.0]]),
    ]
    documents = [
        torch.tensor([[1.0, 0.0], [0.0, 1.0]]),
        torch.tensor([[0.5, 0.5], [-1.0, -1.0]]),
    ]

    actual = memory_efficient_maxsim(queries, documents)
    expected = torch.stack(
        [
            torch.stack([(query @ document.T).amax(dim=1).sum() for document in documents])
            for query in queries
        ]
    )

    assert torch.allclose(actual, expected)


def test_retrieval_metrics_reports_recall_at_1_and_3() -> None:
    scores = torch.tensor(
        [
            [0.9, 0.2, 0.1, 0.0],
            [0.8, 0.7, 0.6, 0.5],
            [0.1, 0.2, 0.3, 0.4],
        ]
    )

    metrics = retrieval_metrics(scores, [0, 2, 1])

    assert metrics.queries == 3
    assert metrics.recall_at_1 == 1 / 3
    assert metrics.recall_at_3 == 1.0
