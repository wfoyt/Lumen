"""Load attachments and build Ollama's text and vision message payloads."""
import base64
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

MAX_ATTACHMENTS = 8
MAX_TEXT_BYTES = 1024 * 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 200


def image_attachment(data, name="Pasted image.png"):
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(f"{name}: maximum image size is 10 MB.")
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format not in ("PNG", "JPEG", "WEBP"):
                raise ValueError(f"{name}: choose a PNG, JPEG or WebP image.")
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError(f"{name}: maximum image resolution is 25 megapixels.")
            image.thumbnail((320, 220))
            image = image.convert("RGBA")
            thumbnail = BytesIO()
            image.save(thumbnail, format="PNG")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError(f"{name}: this image could not be decoded.") from exc
    return {"name": name, "kind": "image", "content": base64.b64encode(data).decode("ascii"),
            "thumbnail": base64.b64encode(thumbnail.getvalue()).decode("ascii")}


def pdf_text(data, name):
    if not data.startswith(b"%PDF-"):
        raise ValueError(f"{name}: this PDF could not be read.")
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError(f"{name}: unlock the password-protected PDF before attaching it.")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ValueError(f"{name}: attach a PDF with at most {MAX_PDF_PAGES} pages.")
        parts, total = [], 0
        for index, page in enumerate(reader.pages):
            content = page.extract_text() or ""
            total += len(content.encode("utf-8"))
            if total > MAX_TEXT_BYTES:
                raise ValueError(f"{name}: extracted PDF text exceeds 1 MB. Attach a smaller document.")
            parts.append(f"Page {index + 1}:\n{content}")
        if not any(part.split("\n", 1)[-1].strip() for part in parts):
            raise ValueError(f"{name}: this PDF has no selectable text. Use an OCR version or attach its pages as images.")
        return "\n\n".join(parts)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"{name}: this PDF could not be read.") from exc


def load_attachment(path, kind):
    path = Path(path)
    is_pdf = kind != "image" and path.suffix.lower() == ".pdf"
    limit = MAX_IMAGE_BYTES if kind == "image" else MAX_PDF_BYTES if is_pdf else MAX_TEXT_BYTES
    with path.open("rb") as source:
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"{path.name}: maximum size is {limit // (1024 * 1024)} MB.")
    pdf = is_pdf or data.startswith(b"%PDF-")
    if kind == "image":
        return image_attachment(data, path.name)
    elif is_pdf or data.startswith(b"%PDF-"):
        content = pdf_text(data, path.name)
    else:
        try:
            content = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError(f"{path.name}: choose a PDF or a UTF-8 text file (such as TXT, Markdown, code or CSV).") from None
        if "\x00" in content:
            raise ValueError(f"{path.name}: this appears to be a binary file. Choose a text file.")
    result = {"name": path.name, "kind": kind, "content": content}
    if pdf:
        result.update(mime="application/pdf", data=base64.b64encode(data).decode("ascii"))
    return result


def user_message(text, attachments):
    prompt = text or "Please analyze the attached files and images."
    content = prompt
    for attachment in attachments:
        if attachment["kind"] == "file":
            content += f"\n\nAttached file: {attachment['name']}\n<attachment>\n{attachment['content']}\n</attachment>"
    message = {"role": "user", "content": content}
    if attachments:
        message["display_content"] = prompt
        message["attachments"] = [{k: a[k] for k in (("name", "kind", "thumbnail") if a["kind"] == "image" else ("name", "kind", "content", "mime", "data")) if k in a} for a in attachments]
    images = [a["content"] for a in attachments if a["kind"] == "image"]
    if images:
        message["images"] = images
    return message
