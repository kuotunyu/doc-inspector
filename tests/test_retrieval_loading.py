"""Offline regression for the single-device adapter without Accelerate."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


def test_single_device_retrieval_without_accelerate(tmp_path: Path) -> None:
    pytest.importorskip("torch", reason="requires local-retrieval extra")
    pytest.importorskip("transformers", reason="requires local-retrieval extra")
    # Reintroducing device_map would make this fail before either forward pass.
    # A fresh interpreter also catches Accelerate imported by lazy dependencies.
    probe = textwrap.dedent(
        """
        import importlib.abc
        import importlib.util
        from pathlib import Path
        import sys
        from unittest.mock import patch

        original_find_spec = importlib.util.find_spec
        def find_spec(name, *args, **kwargs):
            if name == "accelerate" or name.startswith("accelerate."):
                return None
            return original_find_spec(name, *args, **kwargs)
        importlib.util.find_spec = find_spec
        class BlockAccelerate(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "accelerate" or fullname.startswith("accelerate."):
                    raise ModuleNotFoundError("Accelerate must not be required")
        sys.meta_path.insert(0, BlockAccelerate())

        import torch
        from transformers import ColQwen2Config, ColQwen2ForRetrieval, Qwen2VLConfig
        from transformers.feature_extraction_utils import BatchFeature
        from doc_inspector.retrieval import ColQwenRetriever
        from PIL import Image

        torch.manual_seed(7)
        vlm = Qwen2VLConfig(
            text_config={"vocab_size": 64, "hidden_size": 32,
                "intermediate_size": 64, "num_hidden_layers": 1,
                "num_attention_heads": 4, "num_key_value_heads": 2,
                "max_position_embeddings": 128, "bos_token_id": 1, "eos_token_id": 2,
                "rope_parameters": {"rope_type": "default", "mrope_section": [1, 1, 2]}},
            vision_config={"depth": 1, "embed_dim": 32, "hidden_size": 32,
                "num_heads": 4, "mlp_ratio": 2, "patch_size": 2,
                "temporal_patch_size": 1, "spatial_merge_size": 1},
            image_token_id=60, video_token_id=61,
            vision_start_token_id=62, vision_end_token_id=63,
        )
        model = ColQwen2ForRetrieval(ColQwen2Config(vlm_config=vlm, embedding_dim=16))
        assert sum(p.numel() for p in model.parameters()) < 100000
        checkpoint = Path(sys.argv[1]) / "checkpoint"
        model.save_pretrained(checkpoint, safe_serialization=True)
        del model

        # Tokenizer assets are external to this loading regression. Feed valid,
        # fixed multimodal tensors through the adapter into the real tiny model.
        class TensorProcessor:
            def __call__(self, *, text=None, images=None):
                if text is not None:
                    ids = torch.tensor([[1, 2, 3, 4]])
                    return BatchFeature({"input_ids": ids, "attention_mask": torch.ones_like(ids)})
                ids = torch.tensor([[1, 62, 60, 60, 60, 60, 63, 2]])
                return BatchFeature({"input_ids": ids, "attention_mask": torch.ones_like(ids),
                    "pixel_values": torch.zeros(1, 4, 12, dtype=torch.bfloat16),
                    "image_grid_thw": torch.tensor([[1, 2, 2]])})

        with patch("transformers.ColQwen2Processor.from_pretrained", return_value=TensorProcessor()):
            retriever = ColQwenRetriever(str(checkpoint), device="cpu")
            retriever.load()
            loaded_model = retriever.model
            retriever.load()
            assert retriever.model is loaded_model
            text = retriever.embed_queries(["query"])
            image = retriever.embed_images([Image.new("RGB", (2, 2))])
        assert text[0].shape == (4, 16) and image[0].shape == (8, 16)
        assert all(torch.isfinite(e).all() and e.device.type == "cpu" for e in text + image)
        assert next(retriever.model.parameters()).dtype == torch.bfloat16
        assert not retriever.model.training and retriever.load_seconds >= 0
        assert not any(n == "accelerate" or n.startswith("accelerate.") for n in sys.modules)
        print("single-device text/image retrieval PASS without Accelerate")
        """
    )
    env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
               HF_HUB_DISABLE_TELEMETRY="1", CUDA_VISIBLE_DEVICES="", PYTHONIOENCODING="utf-8")
    source = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [source, env.get("PYTHONPATH")]))
    result = subprocess.run([sys.executable, "-c", probe, str(tmp_path)],
                            capture_output=True, text=True, encoding="utf-8", env=env, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
