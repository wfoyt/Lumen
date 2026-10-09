import base64
from io import BytesIO
from pathlib import Path
import tempfile
import unittest

import httpx
import json

from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from ollama_gui.attachments import load_attachment, image_attachment, user_message, MAX_TEXT_BYTES
from ollama_gui.backend import Ollama


class AttachmentTests(unittest.TestCase):
    def test_text_and_image_payload(self):
        with tempfile.TemporaryDirectory() as root:
            text = Path(root) / "notes.md"
            text.write_text("# Notes\nA useful fact.")
            image = Path(root) / "sample.png"
            Image.new("RGB", (30, 20), "blue").save(image)
            attachments = [load_attachment(text, "file"), load_attachment(image, "image")]
            message = user_message("Summarize these", attachments)
            self.assertIn("A useful fact.", message["content"])
            self.assertEqual(base64.b64decode(message["images"][0]), image.read_bytes())
            self.assertEqual(message["display_content"], "Summarize these")
            self.assertEqual(message["attachments"][0], {"name": "notes.md", "kind": "file", "content": attachments[0]["content"]})
            self.assertTrue(user_message("", attachments)["content"].startswith("Please analyze"))
            self.assertIn("thumbnail", message["attachments"][1])
            self.assertEqual(Image.open(BytesIO(base64.b64decode(attachments[1]["thumbnail"]))).size, (30, 20))

    def test_pdf_text_extraction_and_unreadable_documents(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "math.pdf"
            writer = PdfWriter()
            page = writer.add_blank_page(width=300, height=300)
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
            stream = DecodedStreamObject()
            stream.set_data(b"BT /F1 12 Tf 20 200 Td (The answer is 42.) Tj ET")
            page[NameObject("/Contents")] = writer._add_object(stream)
            writer.write(path)
            attachment = load_attachment(path, "file")
            self.assertIn("The answer is 42.", attachment["content"])
            self.assertIn("Page 1:", attachment["content"])
            self.assertEqual(base64.b64decode(attachment["data"]), path.read_bytes())
            self.assertEqual(attachment["mime"], "application/pdf")
            self.assertIn("The answer is 42.", user_message("Summarize", [attachment])["content"])
            writer.encrypt("secret")
            writer.write(path)
            with self.assertRaisesRegex(ValueError, "password-protected"):
                load_attachment(path, "file")
            writer = PdfWriter()
            writer.add_blank_page(width=300, height=300)
            writer.write(path)
            with self.assertRaisesRegex(ValueError, "no selectable text"):
                load_attachment(path, "file")

    def test_pasted_image_validation_and_thumbnail_bounds(self):
        data = BytesIO()
        Image.new("RGB", (1000, 600), "green").save(data, format="PNG")
        attachment = image_attachment(data.getvalue())
        preview = Image.open(BytesIO(base64.b64decode(attachment["thumbnail"])))
        self.assertLessEqual(preview.width, 320)
        self.assertLessEqual(preview.height, 220)
        with self.assertRaises(ValueError):
            image_attachment(b"\x89PNG\r\n\x1a\ninvalid")

    def test_reject_binary_and_oversized_files(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "document.pdf"
            for data, kind in ((b"invalid image", "image"), (b"binary\x00", "file"), (b"\xff", "file"), (b"a" * (MAX_TEXT_BYTES + 1), "file")):
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    load_attachment(path, kind)


class VisionPayloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_api_receives_images_and_text_without_ui_metadata(self):
        message = user_message("Explain", [{"name": "photo.png", "kind": "image", "content": "aW1hZ2U="}, {"name": "note.txt", "kind": "file", "content": "hello from a file"}])
        def handle(request):
            payload = json.loads(request.content)
            sent = payload["messages"][0]
            self.assertEqual(sent["images"], ["aW1hZ2U="])
            self.assertIn("hello from a file", sent["content"])
            self.assertNotIn("display_content", sent)
            self.assertNotIn("attachments", sent)
            return httpx.Response(200, content=json.dumps({"message": {"content": "Understood"}, "done": True}))
        result = await Ollama("http://localhost", httpx.MockTransport(handle)).chat("vision", [message], {}, lambda *_: None)
        self.assertEqual(result[-1]["content"], "Understood")
        self.assertIn("attachments", message)
