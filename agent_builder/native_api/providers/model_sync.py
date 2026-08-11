# native_api/providers/model_sync.py

"""Unified Model Pricing sync — one whitelisted endpoint for every provider.

Design:
  - MODEL_FETCHERS: provider name -> fn(api_key) -> list[raw model dict],
    handling each provider's actual auth scheme and /models response shape.
  - MODEL_EXTRACTORS: provider name -> fn(raw_model) -> Model Pricing fields.
    Falls back to `_extract_generic` (id-only + substring guessing, same
    approach as the original nvidia script) for any provider not yet
    given a dedicated extractor.
  - sync_models(): reads provider + api_key from the *current* Agent Setup
    (single doctype, one active provider at a time) and upserts into
    Model Pricing — same upsert/dry_run shape as the original nvidia script,
    just generic over provider.

GROUNDING / VERIFIED vs ASSUMED (check before trusting a provider's sync):
  - openrouter: VERIFIED. GET /models, no auth required, rich payload —
    pricing (prompt/completion, strings in $/token), context_length,
    supported_parameters array. This is the only provider where pricing +
    context window can be synced automatically today.
  - openai: VERIFIED shape is thin. GET /v1/models -> {data:[{id, object,
    created, owned_by}]}. No pricing, no context window, no capability
    flags in the API at all — OpenAI only publishes those on static docs
    pages. Falls back to id-only + substring guessing.
  - anthropic: VERIFIED shape, DIFFERENT from OpenAI-compat. GET /v1/models
    with header `x-api-key` (not Bearer) + `anthropic-version` header.
    Response: {data:[{id, display_name, created_at, type}]}. Handled with
    its own fetcher below.
  - google: ASSUMED. base_url here is the OpenAI-compat shim
    (generativelanguage.googleapis.com/.../openai), so Bearer auth +
    GET /models is expected to work the same as any OpenAI-compatible
    endpoint, but I have not confirmed the response shape — verify before
    relying on capability guesses for Gemini.
  - xai: ASSUMED OpenAI-compatible (GET /v1/models, Bearer, {data:[...]}).
    Matches xAI's documented OpenAI-compat surface but payload richness
    (context window etc.) not confirmed — treat as id-only for now.
  - nvidia: VERIFIED against your own sync_nvidia_models script — {data:
    [{id, owned_by}]}, no context window, capability flags guessed from
    substrings in the model id (same guesses reused here).
  - mistral, deepseek, groq, cerebras, fireworks, together, deepinfra,
    huggingface, dashscope, nebius, vllm, perplexity: NOT VERIFIED in this
    pass — no config files for them were shared. They default to the
    generic OpenAI-compatible fetcher (Bearer + GET /models) and the
    generic id-only extractor. Some of these (Fireworks, Together,
    DeepInfra in particular) are known to return context_length and
    pricing in their /models payload the way OpenRouter does — worth a
    dedicated extractor later once you confirm the shape, rather than
    leaving them id-only.

Everything landing on "id-only" is intentional per your instruction:
missing pricing/context/capability fields are left at 0/blank for manual
fill-in rather than guessed at with fabricated numbers.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import frappe
import requests

from .registry import get_provider

_TIMEOUT = 30

# ── Capability guessing (shared substring heuristics, from the nvidia script) ──

_VISION_HINTS = ("vision", "vl", "vlm", "pixtral", "llava")
_REASONING_HINTS = ("reason", "reasoning", "nemotron", "thinking", "-r1", "o1", "o3", "o4")


def _guess_vision(model_id: str) -> int:
	return int(any(h in model_id.lower() for h in _VISION_HINTS))


def _guess_reasoning(model_id: str) -> int:
	return int(any(h in model_id.lower() for h in _REASONING_HINTS))


def _base_fields(provider: str, model_id: str, notes: str) -> dict[str, Any]:
	"""Shared skeleton every extractor starts from — keeps field names in
	sync with the Model Pricing DocType in one place."""
	supports_vision = _guess_vision(model_id)
	supports_reasoning = _guess_reasoning(model_id)
	return {
		"provider": provider,
		"model": model_id,
		"context_window": 0,
		"max_output_tokens": 0,
		"supports_tools": 0,
		"supports_vision": supports_vision,
		"supports_reasoning": supports_reasoning,
		"reasoning_efforts": "low,medium,high" if supports_reasoning else "",
		"input_price_per_million": 0,
		"output_price_per_million": 0,
		"cached_price_per_million": 0,
		"notes": notes,
	}


# ── Fetchers: provider -> raw model list ────────────────────────────────


def _fetch_openai_compatible(base_url: str, api_key: str) -> list[dict[str, Any]]:
	"""Works for any provider that mirrors OpenAI's GET /models shape
	({"data": [...]}) with Bearer auth — the default for most providers
	in the registry."""
	resp = requests.get(
		f"{base_url.rstrip('/')}/models",
		headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
		timeout=_TIMEOUT,
	)
	resp.raise_for_status()
	return resp.json().get("data", [])


def _fetch_anthropic(base_url: str, api_key: str) -> list[dict[str, Any]]:
	"""Anthropic uses x-api-key + anthropic-version, not Bearer."""
	resp = requests.get(
		"https://api.anthropic.com/v1/models",
		headers={
			"x-api-key": api_key,
			"anthropic-version": "2023-06-01",
			"Accept": "application/json",
		},
		timeout=_TIMEOUT,
	)
	resp.raise_for_status()
	return resp.json().get("data", [])


def _fetch_openrouter(base_url: str, api_key: str) -> list[dict[str, Any]]:
	"""OpenRouter's /models is public (no auth needed) and richest."""
	resp = requests.get(f"{base_url.rstrip('/')}/models", timeout=_TIMEOUT)
	resp.raise_for_status()
	return resp.json().get("data", [])


MODEL_FETCHERS: dict[str, Callable[[str, str], list[dict[str, Any]]]] = {
	"anthropic": _fetch_anthropic,
	"openrouter": _fetch_openrouter,
	# Everything else defaults to _fetch_openai_compatible in fetch_models().
}


def fetch_models(provider_name: str, base_url: str, api_key: str) -> list[dict[str, Any]]:
	fetcher = MODEL_FETCHERS.get(provider_name, _fetch_openai_compatible)
	return fetcher(base_url, api_key)


# ── Extractors: raw model -> Model Pricing fields ───────────────────────


def _extract_generic(provider: str, model: dict[str, Any]) -> dict[str, Any]:
	"""id-only fallback — same shape as your original nvidia script."""
	model_id = model["id"]
	owned_by = model.get("owned_by")
	notes = "Synced from provider Models API" + (f" — {owned_by}" if owned_by else "")
	return _base_fields(provider, model_id, notes)


def _extract_anthropic(model: dict[str, Any]) -> dict[str, Any]:
	model_id = model["id"]
	fields = _base_fields("anthropic", model_id, f"Synced — {model.get('display_name', '')}".rstrip(" —"))
	fields["supports_tools"] = 1  # every current Claude model supports tool use
	return fields


def _extract_openrouter(model: dict[str, Any]) -> dict[str, Any]:
	model_id = model["id"]
	pricing = model.get("pricing") or {}
	fields = _base_fields("openrouter", model_id, f"Synced from OpenRouter — {model.get('name', '')}".rstrip(" —"))

	fields["context_window"] = int(model.get("context_length") or 0)
	top_provider = model.get("top_provider") or {}
	fields["max_output_tokens"] = int(top_provider.get("max_completion_tokens") or 0)

	# OpenRouter prices are strings, in $ per token — convert to $ per 1M.
	def _per_million(key: str) -> float:
		try:
			return round(float(pricing.get(key, 0)) * 1_000_000, 4)
		except (TypeError, ValueError):
			return 0.0

	fields["input_price_per_million"] = _per_million("prompt")
	fields["output_price_per_million"] = _per_million("completion")
	fields["cached_price_per_million"] = _per_million("input_cache_read")

	supported_params = model.get("supported_parameters") or []
	fields["supports_tools"] = int("tools" in supported_params)
	if "reasoning" in supported_params:
		fields["supports_reasoning"] = 1
		fields["reasoning_efforts"] = "low,medium,high"

	return fields


MODEL_EXTRACTORS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
	"anthropic": _extract_anthropic,
	"openrouter": _extract_openrouter,
	# Everything else defaults to _extract_generic(provider, model) below.
}


def extract_fields(provider_name: str, model: dict[str, Any]) -> dict[str, Any]:
	extractor = MODEL_EXTRACTORS.get(provider_name)
	if extractor is not None:
		return extractor(model)
	return _extract_generic(provider_name, model)


# ── Sync engine (generic upsert, same shape as the original nvidia script) ──


def _upsert(fields: dict[str, Any], dry_run: bool, summary: dict[str, list]) -> None:
	model_id = fields["model"]
	try:
		if frappe.db.exists("Model Pricing", model_id):
			doc = frappe.get_doc("Model Pricing", model_id)
			changed = False
			for key, value in fields.items():
				if key == "notes":
					continue
				if doc.get(key) != value:
					doc.set(key, value)
					changed = True
			if not changed:
				summary["skipped"].append(model_id)
				return
			if not dry_run:
				doc.save(ignore_permissions=True)
			summary["updated"].append(model_id)
		else:
			if not dry_run:
				doc = frappe.new_doc("Model Pricing")
				doc.update(fields)
				doc.insert(ignore_permissions=True)
			summary["created"].append(model_id)
	except Exception as e:
		summary["errors"].append((model_id, str(e)))


@frappe.whitelist()
def sync_models(dry_run: bool = False) -> dict[str, list]:
	"""Sync Model Pricing for whichever provider is currently active in
	Agent Setup. Switch the provider in Agent Setup and call again to
	sync a different one — mirrors how Agent Setup only holds one live
	provider + key at a time.
	"""
	dry_run = frappe.utils.cint(dry_run) if not isinstance(dry_run, bool) else dry_run

	setup = frappe.get_doc("Agent Setup")
	provider_name = (setup.provider or "").strip().lower()
	if not provider_name:
		frappe.throw("Agent Setup has no provider configured.")

	provider = get_provider(provider_name)
	api_key = setup.get_password("api_key")

	raw_models = fetch_models(provider_name, provider.base_url, api_key)

	summary: dict[str, list] = {"created": [], "updated": [], "skipped": [], "errors": []}
	for model in raw_models:
		fields = extract_fields(provider_name, model)
		_upsert(fields, dry_run, summary)

	if not dry_run:
		frappe.db.commit()

	summary["provider"] = provider_name
	return summary