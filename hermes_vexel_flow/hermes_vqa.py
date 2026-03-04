# -----------------------------------------------------------------------------
# SOVEREIGN INTEGRITY PROTOCOL (SIP) LICENSE v1.1
# 
# Copyright (c) 2026, Bradley Wallace (tensorrent). All rights reserved.
# 
# This software, research, and associated mathematical implementations are
# strictly governed by the Sovereign Integrity Protocol (SIP) License v1.1:
# - Personal/Educational Use: Perpetual, worldwide, royalty-free.
# - Commercial Use: Expressly PROHIBITED without a prior written license.
# - Unlicensed Commercial Use: Triggers automatic 8.4% perpetual gross
#   profit penalty (distrust fee + reparation fee).
# 
# See the SIP_LICENSE.md file in the repository root for full terms.
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# SOVEREIGN INTEGRITY PROTOCOL (SIP) LICENSE v1.1
# 
# Copyright (c) 2026, Bradley Wallace (tensorrent). All rights reserved.
# 
# This software, research, and associated mathematical implementations are
# strictly governed by the Sovereign Integrity Protocol (SIP) License v1.1:
# - Personal/Educational Use: Perpetual, worldwide, royalty-free.
# - Commercial Use: Expressly PROHIBITED without a prior written license.
# - Unlicensed Commercial Use: Triggers automatic 8.4% perpetual gross
#   profit penalty (distrust fee + reparation fee).
# 
# See the SIP_LICENSE.md file in the repository root for full terms.
# -----------------------------------------------------------------------------
"""
hermes_vqa.py — Visual Question Answering ↔ Sovereign Stack Bridge
====================================================================
Adds VQA capability to the Hermes + Vexel + Claude Flow stack.

Every image query is cryptographically recorded in the scroll:
  EV_QUERY     — image received, question posed
  EV_RESONANCE — answer acquired (visual knowledge committed)
  EV_MISS      — query failed (model unavailable, image unreadable)

Answers can be optionally committed to MEMORY.md with full vexel
provenance, so the agent "remembers" what it saw and when.

Backends (tried in priority order, first available wins):
  1. claude   — Anthropic claude-sonnet-4-6 vision (ANTHROPIC_API_KEY)
  2. openrouter — Any multimodal model via OpenRouter (OPENROUTER_API_KEY)
  3. blip2    — BLIP-2 via transformers (GPU or CPU, no API key needed)
  4. llava    — LLaVA via Ollama (OLLAMA_HOST, default localhost:11434)
  5. moondream — Moondream2 via transformers (tiny, CPU-friendly, ~2GB)

Scroll event → memory mapping:
  vqa_query(image, question) → EV_QUERY  (visual question posed)
  vqa_answer(answer)         → EV_RESONANCE score=3 (visual knowledge)
  vqa_fail(reason)           → EV_MISS   (query failed)
  vqa_commit(answer)         → MEMORY.md entry with provenance tag

Image input formats accepted:
  - Local file path  (str or Path)
  - HTTP/HTTPS URL
  - base64 data URI  (data:image/jpeg;base64,...)
  - Raw base64 bytes string
  - PIL.Image object (if pillow installed)
  - bytes (raw image bytes)

Usage:
    from hermes_vqa import VQABridge, VQABackend

    bridge = VQABridge(scroll_bridge=hermes_bridge)
    result = bridge.ask(
        image="path/to/image.jpg",
        question="What authentication method is shown in this diagram?",
        commit_to_memory=True,          # → MEMORY.md entry
        memory_label="auth diagram",    # optional label for memory entry
    )
    print(result.answer)
    print(result.vexel_root)    # scroll root after this query
    print(result.backend_used)  # which model answered
"""

import os
import sys
import re
import time
import base64
import hashlib
import mimetypes
import threading
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any

# ── SDK path ──────────────────────────────────────────────────────────────────

SOVEREIGN_SDK = os.environ.get("SOVEREIGN_SDK", os.path.dirname(__file__))
if SOVEREIGN_SDK not in sys.path:
    sys.path.insert(0, SOVEREIGN_SDK)

from vexel_flow import EV_QUERY, EV_RESONANCE, EV_MISS

# ── Configuration ─────────────────────────────────────────────────────────────

DEFAULT_CLAUDE_MODEL     = "claude-sonnet-4-6"
DEFAULT_OPENROUTER_MODEL = "qwen/qwen2.5-vl-7b-instruct"
DEFAULT_BLIP2_MODEL      = "Salesforce/blip2-opt-2.7b"
DEFAULT_MOONDREAM_MODEL  = "vikhyatk/moondream2"
DEFAULT_OLLAMA_MODEL     = "llava:7b"
DEFAULT_OLLAMA_HOST      = "http://localhost:11434"

ANTHROPIC_API_URL    = "https://api.anthropic.com/v1/messages"
OPENROUTER_API_URL   = "https://openrouter.ai/api/v1/chat/completions"
ANTHROPIC_API_VER    = "2023-06-01"

VQA_CACHE_ENABLED = os.environ.get("VQA_CACHE", "1") == "1"

# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class VQAResult:
    question:     str
    answer:       str
    backend_used: str
    image_hash:   str          # SHA-256 of image bytes (first 16 chars)
    vexel_root:   str          # scroll root after answer recorded
    ulam:         tuple        # Ulam position after answer
    latency_ms:   float
    committed:    bool = False  # True if written to MEMORY.md
    memory_entry: str = ""     # The entry written (if committed)
    error:        str = ""

    @property
    def ok(self) -> bool:
        return bool(self.answer) and not self.error


@dataclass
class VQABackendInfo:
    name:      str
    available: bool
    reason:    str = ""


# ── Image loading ─────────────────────────────────────────────────────────────

def load_image_bytes(source: Any) -> tuple[bytes, str]:
    """
    Load image from any supported source.
    Returns (raw_bytes, media_type).
    """
    # PIL Image
    try:
        from PIL import Image as PILImage
        import io
        if isinstance(source, PILImage.Image):
            buf = io.BytesIO()
            fmt = source.format or "JPEG"
            source.save(buf, format=fmt)
            return buf.getvalue(), f"image/{fmt.lower()}"
    except ImportError:
        pass

    # Raw bytes
    if isinstance(source, bytes):
        mt = _detect_mime(source[:16])
        return source, mt

    source = str(source)

    # data URI
    if source.startswith("data:"):
        m = re.match(r"data:([^;]+);base64,(.+)", source, re.DOTALL)
        if m:
            return base64.b64decode(m.group(2)), m.group(1)
        raise ValueError(f"Malformed data URI: {source[:80]}")

    # HTTP/HTTPS URL
    if source.startswith("http://") or source.startswith("https://"):
        req = urllib.request.Request(
            source, headers={"User-Agent": "sovereign-vqa/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        ct = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
        return data, ct

    # Local file
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {source}")
    data = path.read_bytes()
    mt, _ = mimetypes.guess_type(str(path))
    return data, mt or _detect_mime(data[:16])


def _detect_mime(header: bytes) -> str:
    sigs = {
        b"\xff\xd8\xff": "image/jpeg",
        b"\x89PNG":      "image/png",
        b"GIF8":         "image/gif",
        b"RIFF":         "image/webp",
        b"\x00\x00\x00": "image/mp4",  # rough
    }
    for sig, mt in sigs.items():
        if header[:len(sig)] == sig:
            return mt
    return "image/jpeg"


def image_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def to_base64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# ── Backend implementations ───────────────────────────────────────────────────

class _ClaudeBackend:
    """Anthropic claude-sonnet-4-6 vision via REST API."""
    name = "claude"

    def available(self) -> VQABackendInfo:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if key:
            return VQABackendInfo("claude", True)
        return VQABackendInfo("claude", False, "ANTHROPIC_API_KEY not set")

    def ask(self, image_data: bytes, media_type: str,
            question: str, system: str = "") -> str:
        import json, urllib.error
        key   = os.environ["ANTHROPIC_API_KEY"]
        model = os.environ.get("VQA_CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL)
        b64   = to_base64(image_data)

        messages = [{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64",
                             "media_type": media_type,
                             "data": b64}},
                {"type": "text", "text": question},
            ]
        }]

        body = json.dumps({
            "model":      model,
            "max_tokens": 1024,
            "messages":   messages,
            **({"system": system} if system else {}),
        }).encode()

        req = urllib.request.Request(
            ANTHROPIC_API_URL,
            data=body,
            headers={
                "Content-Type":            "application/json",
                "x-api-key":               key,
                "anthropic-version":       ANTHROPIC_API_VER,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read())
        return resp["content"][0]["text"].strip()


class _OpenRouterBackend:
    """Any multimodal model via OpenRouter."""
    name = "openrouter"

    def available(self) -> VQABackendInfo:
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if key:
            return VQABackendInfo("openrouter", True)
        return VQABackendInfo("openrouter", False, "OPENROUTER_API_KEY not set")

    def ask(self, image_data: bytes, media_type: str,
            question: str, system: str = "") -> str:
        import json
        key   = os.environ["OPENROUTER_API_KEY"]
        model = os.environ.get("VQA_OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)
        b64   = to_base64(image_data)
        data_uri = f"data:{media_type};base64,{b64}"

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({
            "role": "user",
            "content": [
                {"type": "image_url",
                 "image_url": {"url": data_uri}},
                {"type": "text", "text": question},
            ]
        })

        body = json.dumps({
            "model":      model,
            "max_tokens": 1024,
            "messages":   messages,
        }).encode()

        req = urllib.request.Request(
            OPENROUTER_API_URL,
            data=body,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {key}",
                "HTTP-Referer":  "https://github.com/sovereign-stack",
                "X-Title":       "sovereign-vqa",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=90) as r:
            resp = json.loads(r.read())
        return resp["choices"][0]["message"]["content"].strip()


class _OllamaBackend:
    """LLaVA (or any vision model) via local Ollama."""
    name = "llava"

    def available(self) -> VQABackendInfo:
        host  = os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)
        model = os.environ.get("VQA_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
        try:
            req = urllib.request.Request(f"{host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3) as r:
                import json
                data   = json.loads(r.read())
                models = [m["name"] for m in data.get("models", [])]
                if any(model.split(":")[0] in m for m in models):
                    return VQABackendInfo("llava", True)
                return VQABackendInfo("llava", False,
                    f"Model {model!r} not pulled in Ollama")
        except Exception as e:
            return VQABackendInfo("llava", False, f"Ollama not reachable: {e}")

    def ask(self, image_data: bytes, media_type: str,
            question: str, system: str = "") -> str:
        import json
        host  = os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)
        model = os.environ.get("VQA_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
        b64   = to_base64(image_data)

        body = json.dumps({
            "model":  model,
            "prompt": question,
            "images": [b64],
            "stream": False,
            **({"system": system} if system else {}),
        }).encode()

        req = urllib.request.Request(
            f"{host}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read())
        return resp["response"].strip()


class _BLIP2Backend:
    """Salesforce BLIP-2 via HuggingFace transformers."""
    name = "blip2"
    _model = None
    _processor = None
    _lock = threading.Lock()

    def available(self) -> VQABackendInfo:
        try:
            import transformers  # noqa
            import torch          # noqa
            return VQABackendInfo("blip2", True)
        except ImportError as e:
            return VQABackendInfo("blip2", False, f"transformers/torch not installed: {e}")

    def _load(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from transformers import Blip2Processor, Blip2ForConditionalGeneration
                    import torch
                    model_id = os.environ.get("VQA_BLIP2_MODEL", DEFAULT_BLIP2_MODEL)
                    device = "cuda" if torch.cuda.is_available() else "cpu"
                    dtype  = torch.float16 if device == "cuda" else torch.float32
                    self._processor = Blip2Processor.from_pretrained(model_id)
                    self._model = Blip2ForConditionalGeneration.from_pretrained(
                        model_id, torch_dtype=dtype, device_map="auto"
                    )

    def ask(self, image_data: bytes, media_type: str,
            question: str, system: str = "") -> str:
        import io, torch
        from PIL import Image
        self._load()
        img    = Image.open(io.BytesIO(image_data)).convert("RGB")
        prompt = f"Question: {question} Answer:"
        inputs = self._processor(img, prompt, return_tensors="pt")
        inputs = {k: v.to(self._model.device) for k, v in inputs.items()}
        with torch.no_grad():
            out = self._model.generate(**inputs, max_new_tokens=256)
        return self._processor.decode(out[0], skip_special_tokens=True).strip()


class _MoondreamBackend:
    """Moondream2 — tiny VLM, CPU-friendly (~2GB)."""
    name = "moondream"
    _model = None
    _lock  = threading.Lock()

    def available(self) -> VQABackendInfo:
        try:
            import transformers  # noqa
            return VQABackendInfo("moondream", True)
        except ImportError as e:
            return VQABackendInfo("moondream", False, str(e))

    def _load(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    import transformers
                    model_id = os.environ.get("VQA_MOONDREAM_MODEL", DEFAULT_MOONDREAM_MODEL)
                    self._model = transformers.pipeline(
                        "image-to-text", model=model_id,
                        trust_remote_code=True,
                    )

    def ask(self, image_data: bytes, media_type: str,
            question: str, system: str = "") -> str:
        import io
        from PIL import Image
        self._load()
        img = Image.open(io.BytesIO(image_data)).convert("RGB")
        result = self._model(img, prompt=question)
        return (result[0].get("generated_text") or "").strip()


# ── Backend registry ──────────────────────────────────────────────────────────

ALL_BACKENDS = [
    _ClaudeBackend(),
    _OpenRouterBackend(),
    _OllamaBackend(),
    _BLIP2Backend(),
    _MoondreamBackend(),
]

BACKEND_MAP = {b.name: b for b in ALL_BACKENDS}


def probe_backends() -> list[VQABackendInfo]:
    """Check availability of all backends."""
    return [b.available() for b in ALL_BACKENDS]


def first_available_backend(preference: str = None):
    """Return the first available backend, respecting preference."""
    if preference:
        b = BACKEND_MAP.get(preference)
        if b:
            info = b.available()
            if info.available:
                return b
            raise RuntimeError(f"Preferred backend {preference!r} not available: {info.reason}")

    for b in ALL_BACKENDS:
        if b.available().available:
            return b
    raise RuntimeError(
        "No VQA backend available. Set ANTHROPIC_API_KEY, OPENROUTER_API_KEY, "
        "start Ollama with a vision model, or install transformers+torch for BLIP2."
    )


# ── Query cache ───────────────────────────────────────────────────────────────

class _VQACache:
    """Simple in-process LRU cache keyed by (image_hash, question, backend)."""

    def __init__(self, max_size: int = 256):
        self._cache: dict[str, VQAResult] = {}
        self._order: list[str]            = []
        self._max   = max_size
        self._lock  = threading.Lock()

    def _key(self, image_hash: str, question: str, backend: str) -> str:
        raw = f"{image_hash}|{question.strip().lower()}|{backend}"
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    def get(self, image_hash: str, question: str, backend: str) -> Optional[VQAResult]:
        if not VQA_CACHE_ENABLED:
            return None
        k = self._key(image_hash, question, backend)
        with self._lock:
            return self._cache.get(k)

    def put(self, image_hash: str, question: str,
            backend: str, result: VQAResult):
        if not VQA_CACHE_ENABLED:
            return
        k = self._key(image_hash, question, backend)
        with self._lock:
            if k not in self._cache:
                self._order.append(k)
            self._cache[k] = result
            if len(self._order) > self._max:
                evict = self._order.pop(0)
                self._cache.pop(evict, None)


_global_cache = _VQACache()


# ── VQABridge ─────────────────────────────────────────────────────────────────

class VQABridge:
    """
    Main interface: image + question → VQAResult, with scroll recording.

    If a HermesScrollBridge is provided, every query/answer is recorded
    as scroll events. Answers can be committed to MEMORY.md.

    Without a bridge, VQABridge still functions — it just doesn't record
    to a scroll (useful for standalone VQA without the full stack).
    """

    def __init__(self,
                 scroll_bridge=None,
                 backend: str = None,
                 system_prompt: str = None):
        """
        Args:
            scroll_bridge: HermesScrollBridge instance (optional).
            backend: Force a specific backend ("claude", "openrouter",
                     "llava", "blip2", "moondream"). Auto-selects if None.
            system_prompt: System context injected into every VQA query.
        """
        self._bridge        = scroll_bridge
        self._backend_pref  = backend
        self._system_prompt = system_prompt or (
            "You are a precise visual analyst embedded in a sovereign AI stack. "
            "Answer questions about images concisely and factually. "
            "If you cannot determine something from the image, say so explicitly."
        )

    def ask(self,
            image: Any,
            question: str,
            commit_to_memory: bool = False,
            memory_label: str = "",
            memory_file: str = "MEMORY.md",
            backend: str = None,
            use_cache: bool = True) -> VQAResult:
        """
        Ask a question about an image.

        Args:
            image: Image source (path, URL, base64, bytes, PIL Image).
            question: Natural language question about the image.
            commit_to_memory: If True, write answer to Hermes MEMORY.md.
            memory_label: Optional label for the memory entry.
            memory_file: "MEMORY.md" or "USER.md".
            backend: Override backend for this call.
            use_cache: Use cached result if available.

        Returns:
            VQAResult with answer, scroll root, backend used, etc.
        """
        t0 = time.time()

        # Load image
        try:
            img_bytes, media_type = load_image_bytes(image)
        except Exception as e:
            return self._fail(question, f"image load failed: {e}")

        img_hash = image_hash(img_bytes)

        # Select backend
        try:
            be = first_available_backend(backend or self._backend_pref)
        except RuntimeError as e:
            return self._fail(question, str(e), img_hash=img_hash)

        # Cache check
        if use_cache:
            cached = _global_cache.get(img_hash, question, be.name)
            if cached:
                # Still record a scroll QUERY event for cache hit
                if self._bridge:
                    self._bridge.scroll.record(
                        f"vqa_cache_hit:{img_hash[:8]}:{question[:48]}",
                        EV_QUERY, 1)
                return cached

        # Record EV_QUERY (visual question posed)
        if self._bridge:
            self._bridge.scroll.record(
                f"vqa_query:{img_hash[:8]}:{question[:64]}",
                EV_QUERY, 1)

        # Query backend
        try:
            answer = be.ask(img_bytes, media_type, question, self._system_prompt)
        except Exception as e:
            if self._bridge:
                self._bridge.scroll.record(
                    f"vqa_fail:{be.name}:{str(e)[:48]}", EV_MISS, 0)
            return self._fail(question, f"{be.name} error: {e}", img_hash=img_hash,
                              backend=be.name)

        # Record EV_RESONANCE (visual knowledge acquired)
        vexel_root = "0x0000000000000000"
        ulam       = (0, 0)
        if self._bridge:
            self._bridge.scroll.record(
                f"vqa_answer:{img_hash[:8]}:{answer[:48]}",
                EV_RESONANCE, 3)
            vexel_root = self._bridge.scroll.eigen()
            ulam       = self._bridge.scroll.ulam()

        latency = (time.time() - t0) * 1000

        result = VQAResult(
            question     = question,
            answer       = answer,
            backend_used = be.name,
            image_hash   = img_hash,
            vexel_root   = vexel_root,
            ulam         = ulam,
            latency_ms   = latency,
        )

        # Commit to MEMORY.md
        if commit_to_memory and self._bridge:
            result = self._commit(result, memory_label, memory_file)

        # Cache
        _global_cache.put(img_hash, question, be.name, result)

        return result

    def ask_batch(self, image: Any, questions: list[str],
                  commit_to_memory: bool = False,
                  memory_file: str = "MEMORY.md",
                  backend: str = None) -> list[VQAResult]:
        """Ask multiple questions about the same image."""
        try:
            img_bytes, media_type = load_image_bytes(image)
        except Exception as e:
            return [self._fail(q, f"image load failed: {e}") for q in questions]

        results = []
        for q in questions:
            r = self.ask(img_bytes, q,
                         commit_to_memory=commit_to_memory,
                         memory_file=memory_file,
                         backend=backend)
            results.append(r)
        return results

    def describe(self, image: Any,
                 commit_to_memory: bool = False,
                 memory_label: str = "image observation",
                 backend: str = None) -> VQAResult:
        """Get a general description of an image."""
        return self.ask(
            image,
            "Describe this image in detail. What do you see?",
            commit_to_memory=commit_to_memory,
            memory_label=memory_label,
            backend=backend,
        )

    def extract_text(self, image: Any,
                     commit_to_memory: bool = False,
                     backend: str = None) -> VQAResult:
        """Extract text visible in an image (OCR-style)."""
        return self.ask(
            image,
            "Extract all text visible in this image, preserving formatting where possible.",
            commit_to_memory=commit_to_memory,
            memory_label="extracted text",
            backend=backend,
        )

    def classify(self, image: Any, categories: list[str],
                 commit_to_memory: bool = False,
                 backend: str = None) -> VQAResult:
        """Classify image into one of the given categories."""
        cats = ", ".join(f'"{c}"' for c in categories)
        return self.ask(
            image,
            f"Which of these categories best describes this image: {cats}? "
            f"Reply with the category name only.",
            commit_to_memory=commit_to_memory,
            memory_label=f"image classification",
            backend=backend,
        )

    def _commit(self, result: VQAResult,
                label: str, memory_file: str) -> VQAResult:
        """Write answer to Hermes MEMORY.md with vexel provenance."""
        label_str = f" [{label}]" if label else ""
        q_short   = result.question[:80].rstrip()
        a_short   = result.answer[:200].rstrip()
        entry     = (f"VQA{label_str}: {q_short} → {a_short} "
                     f"[img:{result.image_hash[:8]}, {result.backend_used}]")

        mem_result = self._bridge.memory_add(entry, memory_file)

        result.committed    = mem_result.get("ok", False)
        result.memory_entry = entry
        # Update root after memory write
        result.vexel_root   = self._bridge.scroll.eigen()
        result.ulam         = self._bridge.scroll.ulam()
        return result

    def _fail(self, question: str, error: str,
              img_hash: str = "", backend: str = "") -> VQAResult:
        return VQAResult(
            question     = question,
            answer       = "",
            backend_used = backend,
            image_hash   = img_hash,
            vexel_root   = "0x0000000000000000",
            ulam         = (0, 0),
            latency_ms   = 0.0,
            error        = error,
        )

    def status(self) -> dict:
        """Return backend availability status."""
        backends = []
        for info in probe_backends():
            backends.append({
                "name":      info.name,
                "available": info.available,
                "reason":    info.reason,
            })
        return {
            "backends":         backends,
            "active_backend":   next((b["name"] for b in backends if b["available"]), None),
            "cache_enabled":    VQA_CACHE_ENABLED,
            "bridge_attached":  self._bridge is not None,
        }


# ── Standalone VQA (no bridge) ────────────────────────────────────────────────

def quick_ask(image: Any, question: str, backend: str = None) -> str:
    """One-liner VQA without a scroll bridge."""
    vqa = VQABridge()
    r   = vqa.ask(image, question, backend=backend)
    if not r.ok:
        raise RuntimeError(r.error)
    return r.answer


# ── Hermes tool interception ──────────────────────────────────────────────────
#
# Called by hermes_hooks.py when the Hermes model uses a `vqa` tool.
# Tool schema (what the model sees):
#
#   vqa(
#     image_source: str,      # path, URL, or base64 data URI
#     question: str,
#     commit: bool = false,   # write answer to MEMORY.md?
#     label: str = "",
#     backend: str = "",      # force backend ("claude", "llava", etc.)
#   ) → {"answer": str, "vexel_root": str, "backend": str}

def handle_vqa_tool(tool_input: dict, scroll_bridge=None) -> dict:
    """
    Entry point for hermes_hooks interception of the `vqa` tool.
    Returns a dict that becomes the tool result visible to the model.
    """
    image_source = (tool_input.get("image_source") or
                    tool_input.get("image") or
                    tool_input.get("path") or "")
    question     = tool_input.get("question") or tool_input.get("q") or ""
    commit       = tool_input.get("commit", False)
    label        = tool_input.get("label", "")
    backend_pref = tool_input.get("backend", "") or None
    memory_file  = tool_input.get("memory_file", "MEMORY.md")

    if not image_source:
        return {"error": "vqa tool: image_source is required"}
    if not question:
        return {"error": "vqa tool: question is required"}

    vqa    = VQABridge(scroll_bridge=scroll_bridge, backend=backend_pref)
    result = vqa.ask(
        image_source, question,
        commit_to_memory=bool(commit),
        memory_label=label,
        memory_file=memory_file,
        backend=backend_pref,
    )

    if not result.ok:
        return {"error": result.error, "vexel_root": result.vexel_root}

    return {
        "answer":       result.answer,
        "vexel_root":   result.vexel_root,
        "ulam":         list(result.ulam),
        "backend":      result.backend_used,
        "image_hash":   result.image_hash,
        "latency_ms":   round(result.latency_ms, 1),
        "committed":    result.committed,
        "memory_entry": result.memory_entry,
    }


# ── VQA tool schema (for Hermes model_tools registration) ────────────────────

VQA_TOOL_SCHEMA = {
    "name":        "vqa",
    "description": (
        "Ask a question about an image. The answer is automatically recorded "
        "in the vexel scroll and optionally committed to MEMORY.md. "
        "Supports local files, URLs, and base64 data URIs."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "image_source": {
                "type":        "string",
                "description": "Image source: file path, HTTP URL, or data:image/...;base64,... URI"
            },
            "question": {
                "type":        "string",
                "description": "Question to ask about the image"
            },
            "commit": {
                "type":        "boolean",
                "description": "If true, write the answer to MEMORY.md",
                "default":     False
            },
            "label": {
                "type":        "string",
                "description": "Optional label for the MEMORY.md entry",
                "default":     ""
            },
            "backend": {
                "type":        "string",
                "description": "Force a specific backend: claude, openrouter, llava, blip2, moondream",
                "enum":        ["", "claude", "openrouter", "llava", "blip2", "moondream"],
                "default":     ""
            },
        },
        "required": ["image_source", "question"]
    }
}


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, json

    parser = argparse.ArgumentParser(description="Sovereign VQA CLI")
    sub    = parser.add_subparsers(dest="cmd")

    # status
    sub.add_parser("status", help="Check backend availability")

    # ask
    ask_p = sub.add_parser("ask", help="Ask a question about an image")
    ask_p.add_argument("image",    help="Image path, URL, or data URI")
    ask_p.add_argument("question", help="Question to ask")
    ask_p.add_argument("--backend", default=None)
    ask_p.add_argument("--commit",  action="store_true",
                       help="Write answer to MEMORY.md")

    # describe
    desc_p = sub.add_parser("describe", help="Describe an image")
    desc_p.add_argument("image")
    desc_p.add_argument("--backend", default=None)

    # demo
    sub.add_parser("demo", help="Run self-test demo")

    args = parser.parse_args()

    if args.cmd == "status":
        vqa = VQABridge()
        st  = vqa.status()
        for b in st["backends"]:
            mark = "✓" if b["available"] else "✗"
            note = f"  ({b['reason']})" if not b["available"] else ""
            print(f"  {mark} {b['name']}{note}")
        print(f"\n  Active: {st['active_backend'] or 'none'}")

    elif args.cmd == "ask":
        vqa = VQABridge()
        r   = vqa.ask(args.image, args.question, backend=args.backend,
                      commit_to_memory=args.commit)
        if r.ok:
            print(f"\nAnswer:  {r.answer}")
            print(f"Backend: {r.backend_used}  ({r.latency_ms:.0f}ms)")
            print(f"Root:    {r.vexel_root}")
        else:
            print(f"Error: {r.error}", file=sys.stderr)
            sys.exit(1)

    elif args.cmd == "describe":
        vqa = VQABridge()
        r   = vqa.describe(args.image, backend=args.backend)
        if r.ok:
            print(r.answer)
        else:
            print(f"Error: {r.error}", file=sys.stderr)
            sys.exit(1)

    elif args.cmd == "demo":
        print(f"\n{'═'*60}")
        print("  HERMES VQA DEMO (no image needed)")
        print(f"{'═'*60}\n")

        # Backend probe
        print("  Backend availability:")
        for info in probe_backends():
            mark = "✓" if info.available else "✗"
            note = f"  — {info.reason}" if not info.available else ""
            print(f"    {mark} {info.name}{note}")

        # Show tool schema
        print(f"\n  VQA tool schema registered as: {VQA_TOOL_SCHEMA['name']!r}")

        # Simulate tool interception without a real image
        print("\n  Simulating handle_vqa_tool() with mock result...")
        mock_result = {
            "answer":     "The diagram shows JWT RS256 token flow with PKCE.",
            "vexel_root": "0xdeadbeef12345678",
            "ulam":       [-4, 26],
            "backend":    "claude",
            "image_hash": "abc123def456abcd",
            "latency_ms": 342.0,
            "committed":  False,
            "memory_entry": "",
        }
        print(f"    answer:   {mock_result['answer']}")
        print(f"    backend:  {mock_result['backend']}")
        print(f"    root:     {mock_result['vexel_root']}")

        # Show scroll event mapping
        print("\n  Scroll event mapping:")
        print("    vqa_query(image, question) → EV_QUERY  score=1")
        print("    vqa_answer(answer)         → EV_RESONANCE score=3")
        print("    vqa_fail(reason)           → EV_MISS  score=0")
        print("    vqa_commit(entry)          → MEMORY.md + provenance tag")

        print(f"\n{'─'*60}")
        print("  VQA bridge ready. Set ANTHROPIC_API_KEY to activate.")
        print(f"{'─'*60}\n")

    else:
        parser.print_help()
