import os
import re
import json
import glob
import subprocess
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
import pytesseract
from PIL import Image

CHANNEL_ID = os.environ["CHANNEL_ID"]
PHONE = os.environ["WHATSAPP_PHONE"]
APIKEY = os.environ["CALLMEBOT_KEY"]
SEEN = Path("vistos.json")

KEY = r"(?:code|promo|promocode|c[oó]digo|промокод|код)"
CODE_RE = re.compile(rf"{KEY}\W{{0,5}}\s*[:\-]?\s*([A-Za-z0-9]{{5,20}})", re.I)
CAPS_RE = re.compile(r"\b(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*[0-9])[A-Z0-9]{6,16}\b")
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}


def videos():
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
    root = ET.fromstring(requests.get(url, timeout=20).content)
    for e in root.findall("a:entry", NS):
        yield e.find("yt:videoId", NS).text, e.find("a:title", NS).text


def ocr_video(video_id):
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/v.mp4"
        subprocess.run(
            ["yt-dlp", "-f", "worst[height>=360]/worst", "--max-filesize", "150M",
             "-o", path, f"https://youtu.be/{video_id}"],
            check=True, timeout=600,
        )
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-i", path, "-vf", "fps=1/2",
             f"{tmp}/f_%05d.png"],
            check=True, timeout=600,
        )
        texto = []
        for f in sorted(glob.glob(f"{tmp}/f_*.png")):
            texto.append(pytesseract.image_to_string(Image.open(f)))
        return "\n".join(texto)


def extrair(texto):
    fortes = {m.group(1).upper() for m in CODE_RE.finditer(texto)}
    fracos = set(CAPS_RE.findall(texto)) - fortes
    return fortes, fracos


def enviar(msg):
    requests.get(
        "https://api.callmebot.com/whatsapp.php",
        params={"phone": PHONE, "text": msg, "apikey": APIKEY},
        timeout=30,
    )


def main():
    primeira = not SEEN.exists()
    vistos = set(json.loads(SEEN.read_text())) if SEEN.exists() else set()
    lista = list(videos())

    if primeira:
        vistos.update(v for v, _ in lista[1:])
        lista = lista[:1]

    for vid, titulo in lista:
        if vid in vistos:
            continue
        link = f"https://youtu.be/{vid}"
        try:
            fortes, fracos = extrair(ocr_video(vid))
        except Exception as ex:
            enviar(f"Novo vídeo: {titulo}\n{link}\n(não consegui ler: {ex})")
            vistos.add(vid)
            continue
        msg = f"🎮 {titulo}\n{link}\n"
        if fortes:
            msg += "🔑 Códigos: " + ", ".join(sorted(fortes)) + "\n"
        if fracos:
            msg += "❓ Possíveis: " + ", ".join(sorted(fracos)[:10])
        if not fortes and not fracos:
            msg += "Nenhum código detectado."
        enviar(msg)
        vistos.add(vid)

    SEEN.write_text(json.dumps(sorted(vistos)))


if __name__ == "__main__":
    main()
