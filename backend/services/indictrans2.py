"""Graceful IndicTrans2 wrapper. Lazily loads model on first call (singleton).

Environment:
    INDICTRANS2_MODEL — HuggingFace model name (default: ai4bharat/indictrans2-indic-en-dist-200M)

If torch or transformers are not installed, is_available() returns False
and translate() returns None — caller handles fallback.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_MODEL = None
_TOKENIZER = None
_DEVICE = None


def is_available() -> bool:
    """Check if IndicTrans2 can actually be loaded in this environment."""
    if _MODEL is not None:
        return True
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


async def _load():
    global _MODEL, _TOKENIZER, _DEVICE
    if _MODEL is not None:
        return

    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    model_name = os.environ.get(
        "INDICTRANS2_MODEL",
        "ai4bharat/indictrans2-indic-en-dist-200M",
    )
    _DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("Loading IndicTrans2 model %s on %s …", model_name, _DEVICE)

    _TOKENIZER = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    _MODEL = AutoModelForSeq2SeqLM.from_pretrained(
        model_name, trust_remote_code=True
    ).to(_DEVICE)
    _MODEL.eval()
    logger.info("IndicTrans2 model loaded successfully.")


async def translate(text: str, src: str = "te", tgt: str = "en") -> str | None:
    """Translate a single string. Returns None if model isn't available."""
    if not is_available():
        logger.warning("IndicTrans2 unavailable (torch/transformers not installed)")
        return None
    try:
        await _load()
        import torch

        batch = _TOKENIZER([text], return_tensors="pt", padding=True, truncation=True).to(_DEVICE)
        with torch.no_grad():
            outputs = _MODEL.generate(
                **batch,
                forced_bos_token_id=_TOKENIZER.get_lang_id(f"{tgt}_XXX"),
                max_length=256,
            )
        return _TOKENIZER.batch_decode(outputs, skip_special_tokens=True)[0]
    except Exception as exc:
        logger.exception("IndicTrans2 translate() failed: %s", exc)
        return None


async def translate_batch(texts: list[str], src: str = "te", tgt: str = "en") -> list[str | None]:
    """Translate a batch of strings. Returns None for texts where translation failed."""
    if not is_available():
        logger.warning("IndicTrans2 unavailable for batch (torch/transformers not installed)")
        return [None] * len(texts)
    try:
        await _load()
        import torch

        batch = _TOKENIZER(texts, return_tensors="pt", padding=True, truncation=True).to(_DEVICE)
        with torch.no_grad():
            outputs = _MODEL.generate(
                **batch,
                forced_bos_token_id=_TOKENIZER.get_lang_id(f"{tgt}_XXX"),
                max_length=256,
            )
        return _TOKENIZER.batch_decode(outputs, skip_special_tokens=True)
    except Exception as exc:
        logger.exception("IndicTrans2 translate_batch() failed: %s", exc)
        return [None] * len(texts)
