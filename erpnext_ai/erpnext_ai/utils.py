# Copyright (c) 2026, Plus Care and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def check_ai_access(settings):
	"""Server-side gate for every AI feature, not just the chat widget.

	The client-side widget/page hides itself based on boot info, but that's a
	UX nicety — this is the actual permission boundary, so every AI feature
	must route through here (or an equivalent check) rather than trusting the
	client.
	"""
	if not settings.enabled:
		frappe.throw(_("The AI assistant is not enabled"), frappe.PermissionError)

	if settings.allowed_role not in frappe.get_roles():
		frappe.throw(_("You are not permitted to use the AI assistant"), frappe.PermissionError)


def extract_text_from_file(file_doc) -> str:
	"""Extract plain text from a File doc's content (.pdf, .docx, or plain text)."""
	content = file_doc.get_content()
	filename = (file_doc.file_name or "").lower()

	if filename.endswith(".pdf"):
		import io

		from pypdf import PdfReader

		reader = PdfReader(io.BytesIO(content))
		return "\n".join(page.extract_text() or "" for page in reader.pages)

	if filename.endswith(".docx"):
		import io

		from docx import Document as DocxDocument

		doc = DocxDocument(io.BytesIO(content))
		return "\n".join(p.text for p in doc.paragraphs)

	if isinstance(content, bytes):
		return content.decode("utf-8", errors="ignore")
	return content or ""


def extract_json_object(text: str) -> dict:
	"""Best-effort parse of a JSON object the LLM may have wrapped in prose/code fences."""
	import json
	import re

	text = (text or "").strip()
	match = re.search(r"\{.*\}", text, re.DOTALL)
	if match:
		text = match.group(0)
	try:
		return json.loads(text)
	except (ValueError, TypeError):
		return {}


def extract_json_list(text: str) -> list:
	"""Best-effort parse of a JSON array the LLM may have wrapped in prose/code fences."""
	import json
	import re

	text = (text or "").strip()
	match = re.search(r"\[.*\]", text, re.DOTALL)
	if match:
		text = match.group(0)
	try:
		data = json.loads(text)
		return data if isinstance(data, list) else []
	except (ValueError, TypeError):
		return []


MAX_IMAGE_BYTES = 5 * 1024 * 1024
_FETCH_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ERPNextAI/1.0)"}


def _assert_public_url(url: str):
	"""Refuse anything but http(s) URLs that resolve to public addresses (SSRF guard)."""
	import ipaddress
	import socket
	from urllib.parse import urlparse

	parsed = urlparse(url)
	if parsed.scheme not in ("http", "https") or not parsed.hostname:
		frappe.throw(_("Invalid URL"))
	try:
		infos = socket.getaddrinfo(parsed.hostname, None)
	except socket.gaierror:
		frappe.throw(_("Could not resolve {0}").format(parsed.hostname))
	for info in infos:
		if not ipaddress.ip_address(info[4][0]).is_global:
			frappe.throw(_("URL points to a non-public address"))


def _safe_get(url: str, max_bytes: int, timeout: int = 10):
	"""GET `url`, following up to 3 redirects and re-checking each hop. Returns (content, content_type)."""
	from urllib.parse import urljoin

	import requests

	for _hop in range(4):
		_assert_public_url(url)
		with requests.get(
			url, headers=_FETCH_HEADERS, timeout=timeout, stream=True, allow_redirects=False
		) as r:
			if r.is_redirect:
				url = urljoin(url, r.headers.get("Location", ""))
				continue
			r.raise_for_status()
			content = b""
			for chunk in r.iter_content(64 * 1024):
				content += chunk
				if len(content) > max_bytes:
					frappe.throw(_("File is too large"))
			return content, (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
	frappe.throw(_("Too many redirects"))


def download_image(url: str):
	"""Download an image URL; returns (bytes, file_name). Throws if it isn't a small real image."""
	import os
	from urllib.parse import urlparse

	try:
		content, content_type = _safe_get(url, MAX_IMAGE_BYTES)
	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.throw(_("Could not download the image: {0}").format(str(e)))
	if not content_type.startswith("image/") or content_type == "image/svg+xml":
		frappe.throw(_("The link is not a usable image"))

	name = os.path.basename(urlparse(url).path) or "item-image"
	if "." not in name:
		name += "." + content_type.split("/")[1].replace("jpeg", "jpg")
	return content, name


def extract_page_images(page_url: str) -> list:
	"""Image URLs a product page advertises (og:image / twitter:image), best effort.

	Pages that fail to load or block us just yield nothing.
	"""
	from urllib.parse import urljoin

	from bs4 import BeautifulSoup

	try:
		content, content_type = _safe_get(page_url, 2 * 1024 * 1024)
	except Exception:
		return []
	if "html" not in content_type:
		return []

	soup = BeautifulSoup(content, "html.parser")
	urls = []
	for attr, name in (("property", "og:image"), ("name", "twitter:image"), ("property", "og:image:secure_url")):
		for tag in soup.find_all("meta", attrs={attr: name}):
			src = (tag.get("content") or "").strip()
			if src:
				urls.append(urljoin(page_url, src))
	return list(dict.fromkeys(urls))
