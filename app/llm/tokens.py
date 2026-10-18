"""Estimate whether a prompt fits the model's context window, without a tokenizer."""

# Measured on 2026-10-17 with `qwen2.5:14b` and the answering prompt: 3.07 to 3.19 characters per token. Rounded down,
# so the estimate errs towards more tokens.
CHARS_PER_TOKEN = 3.0
# Extra room left on top of that, as the estimate is not exact.
SAFETY_MARGIN = 0.05


def estimate_tokens(text: str) -> int:
    """Estimate how many tokens the text takes, from its length."""
    return round(len(text) / CHARS_PER_TOKEN)


def fits_context(text: str, context_tokens: int | None) -> bool:
    """Say whether the text is estimated to fit the window with the safety margin; no window means it always fits."""
    return context_tokens is None or estimate_tokens(text) <= context_tokens * (1 - SAFETY_MARGIN)
