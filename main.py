import os
import time
import pickle
import numpy as np

from moviepy.editor import VideoFileClip, concatenate_videoclips
from moviepy.video.fx.all import crop

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


# ======================
# AYARLAR
# ======================
INPUT_FOLDER = "ham_videolar"
OUTPUT_FOLDER = "islenenler"

CLIENT_SECRET_FILE = "client_secret.json"
TOKEN_FILE = "token.pickle"

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

MAX_SHORT_DURATION = 60        # saniye
UPLOAD_INTERVAL = 8 * 60 * 60  # 8 saat


os.makedirs(INPUT_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


# ======================
# OAUTH 2.0 (TOKEN OLUŞTURMA)
# ======================
def get_youtube_service():
    creds = None

    # Daha önce token varsa oku
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    # Token yoksa / geçersizse
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE,
                SCOPES
            )
            creds = flow.run_local_server(port=0)

        # token.pickle oluşturulur
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return build("youtube", "v3", credentials=creds)


# ======================
# SESSİZLİK KESME (JUMPCUT)
# ======================
def remove_silence(clip, threshold=0.02, min_chunk=0.3):
    if clip.audio is None:
        return clip

    fps = 44100
    samples = clip.audio.to_soundarray(fps=fps)
    volume = np.linalg.norm(samples, axis=1)

    mask = volume > threshold
    times = np.arange(len(mask)) / fps

    chunks = []
    start = None

    for t, m in zip(times, mask):
        if m and start is None:
            start = t
        elif not m and start is not None:
            if t - start >= min_chunk:
                chunks.append(clip.subclip(start, t))
            start = None

    if start is not None:
        end = times[-1]
        if end - start >= min_chunk:
            chunks.append(clip.subclip(start, end))

    if not chunks:
        return clip

    return concatenate_videoclips(chunks)


# ======================
# SHORTS FORMAT (9:16)
# ======================
def to_vertical_short(clip):
    w, h = clip.size
    target_ratio = 9 / 16
    target_w = min(w, h * target_ratio)

    vertical = crop(
        clip,
        width=target_w,
        height=h,
        x_center=w / 2,
        y_center=h / 2
    )

    if vertical.duration > MAX_SHORT_DURATION:
        vertical = vertical.subclip(0, MAX_SHORT_DURATION)

    return vertical


# ======================
# VIDEO İŞLEME
# ======================
def process_video(video_path):
    clip = VideoFileClip(video_path)

    clip = remove_silence(clip)
    clip = to_vertical_short(clip)

    output_path = os.path.join(
        OUTPUT_FOLDER,
        "PROCESSED_" + os.path.basename(video_path)
    )

    clip.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac"
    )

    clip.close()
    return output_path


# ======================
# YOUTUBE UPLOAD
# ======================
def upload_to_youtube(youtube, file_path):
    title_base = os.path.splitext(os.path.basename(file_path))[0]
    title_base = title_base.replace("PROCESSED_", "")

    body = {
        "snippet": {
            "title": f"{title_base} #shorts",
            "description": "Yapay zeka ile otomatik yüklenmiştir.",
            "categoryId": "20"
        },
        "status": {
            "privacyStatus": "public"
        }
    }

    media = MediaFileUpload(
        file_path,
        mimetype="video/mp4",
        resumable=True
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = request.execute()
    print("Yüklendi! Video ID:", response["id"])


# ======================
# OTOMASYON DÖNGÜSÜ
# ======================
def start_automation():
    youtube = get_youtube_service()

    while True:
        videos = [
            v for v in os.listdir(INPUT_FOLDER)
            if v.lower().endswith((".mp4", ".mov", ".mkv"))
        ]

        if not videos:
            print("Klasör boş, bekleniyor...")
            time.sleep(60)
            continue

        for video in videos[:1]:  # günde 3 için → 3 yap
            input_path = os.path.join(INPUT_FOLDER, video)

            try:
                print("İşleniyor:", video)
                processed = process_video(input_path)
                upload_to_youtube(youtube, processed)

                os.remove(input_path)
                print("Başarıyla tamamlandı.")

                time.sleep(UPLOAD_INTERVAL)

            except Exception as e:
                print("HATA:", e)
                print("Video silinmedi.")
                time.sleep(300)


if __name__ == "__main__":
    start_automation()
