# agent_builder/native_api/agent/attachments.py
"""Build OpenAI/OpenRouter-style multimodal `content` parts from attachments.

Attachments arrive as [{"file_name": ..., "file_url": ..., "mime_type": ...}, ...]
— uploaded client-side via Frappe's `upload_file` endpoint as *private*
files (see chat_ui.js's uploadFiles()). Their file_url (e.g.
"/private/files/foo.png") is not publicly reachable, so instead of handing
the URL to the provider we read the bytes off disk ourselves and inline
them as base64 `data:` URLs — this works for OpenRouter (and any
OpenAI-compatible provider) regardless of whether the site is internet-
facing.

Two content types are produced, per OpenRouter's multimodal API
(https://openrouter.ai/docs/guides/overview/multimodal/overview):

  - images  -> {"type": "image_url", "image_url": {"url": "data:..."}}
  - PDFs    -> {"type": "file", "file": {"filename": ..., "file_data": "data:..."}}

PDFs are sent for *any* model — OpenRouter parses them server-side (native
model support first, falling back to its own OCR pipeline) regardless of
whether the target model natively accepts file input. Images are only
inlined when the caller says the resolved model supports vision
(Model Pricing.supports_vision); otherwise they're dropped and mentioned
by filename in the text instead, same as the old behavior. Any other file
type (docx, csv, ...) isn't reliably inlinable via either content type, so
it's always left as a filename reference in the text.
"""

from __future__ import annotations

import base64
import mimetypes
from typing import Any

import frappe

_PDF_MIME = "application/pdf"


def _guess_mime(file_name: str) -> str:
	mime, _ = mimetypes.guess_type(file_name or "")
	return mime or "application/octet-stream"


def _read_as_data_url(file_url: str, mime_type: str) -> str | None:
	"""Read a Frappe-managed file (private or public) and return a base64
	data: URL. Returns None (never raises) if the file can't be read —
	callers should drop that attachment rather than fail the whole turn."""
	if not file_url:
		return None
	try:
		file_doc = frappe.get_doc("File", {"file_url": file_url})
		content = file_doc.get_content()
		if isinstance(content, str):
			content = content.encode("utf-8")
		b64 = base64.b64encode(content).decode("ascii")
		return f"data:{mime_type};base64,{b64}"
	except Exception:
		frappe.log_error("Attachment read failed", frappe.get_traceback())
		return None


def has_pdf_attachment(attachments: list[dict[str, Any]] | None) -> bool:
	"""True if any attachment is a PDF — used by OpenAIProvider to decide
	whether to send OpenRouter's `plugins: [{id: "file-parser", ...}]`
	request field configuring the PDF-parsing engine."""
	if not attachments:
		return False
	for a in attachments:
		file_name = a.get("file_name") or ""
		mime_type = a.get("mime_type") or _guess_mime(file_name)
		if mime_type == _PDF_MIME:
			return True
	return False


def build_content_parts(
	text: str,
	attachments: list[dict[str, Any]] | None,
	*,
	allow_images: bool = True,
) -> str | list[dict[str, Any]]:
	"""Turn (text, attachments) into an OpenAI/OpenRouter `content` value.

	Returns a plain string when there are no attachments worth inlining
	(the common case — output is byte-identical to the old text-only
	behavior), or a content-parts array — [text part, image_url/file
	parts...] — when at least one attachment was inlined.

	allow_images: pass False when the resolved model doesn't advertise
	vision support. Image attachments are then skipped (and noted by
	filename in the text) rather than sent as bytes the model will 400 on.
	PDFs are never gated this way — see module docstring.
	"""
	if not attachments:
		return text or ""

	parts: list[dict[str, Any]] = []
	skipped: list[str] = []

	for a in attachments:
		file_url = a.get("file_url") or ""
		file_name = a.get("file_name") or (file_url.rsplit("/", 1)[-1] if file_url else "file")
		mime_type = a.get("mime_type") or _guess_mime(file_name)

		is_image = mime_type.startswith("image/")
		is_pdf = mime_type == _PDF_MIME

		if not (is_image or is_pdf):
			# Not something we can reliably inline (docx, csv, etc.) —
			# leave it as a text reference, same as before this feature.
			skipped.append(file_name)
			continue

		if is_image and not allow_images:
			skipped.append(file_name)
			continue

		data_url = _read_as_data_url(file_url, mime_type)
		if not data_url:
			skipped.append(file_name)
			continue

		if is_image:
			parts.append({"type": "image_url", "image_url": {"url": data_url}})
		else:
			parts.append({"type": "file", "file": {"filename": file_name, "file_data": data_url}})

	body_text = text or ""
	if skipped:
		refs = "\n".join(f"- {n}" for n in skipped)
		note = f"\n\n[Attached files the model can't view directly]\n{refs}"
		body_text = f"{body_text}{note}".strip()

	if not parts:
		return body_text

	parts.insert(0, {"type": "text", "text": body_text})
	return parts