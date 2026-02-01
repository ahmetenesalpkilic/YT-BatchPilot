import os
import pickle
import shutil
import datetime

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# ======================
# AYARLAR
# ======================
INPUT_FOLDER = "ham_videolar"
DESTINATION_FOLDER = "islenmis_videolar"
LOG_FILE = "planlanan_tarihler.txt"

CLIENT_SECRET_FILE = "client_secret.json"
TOKEN_FILE = "token.pickle"

SCOPES = ["https://www.googleapis.com/auth/youtube"]

SCHEDULE_TIMES = [
    "13:00:00+03:00",
    "17:00:00+03:00"
]

os.makedirs(DESTINATION_FOLDER, exist_ok=True)

# ======================
# YOUTUBE BAĞLANTISI
# ======================
def get_youtube_service():
    creds = None

    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0, prompt="select_account")

        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return build("youtube", "v3", credentials=creds)

# ======================
# TARİH TAKİP SİSTEMİ
# ======================
def get_next_available_dates(count_days=2):
    planned_dates = []

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            planned_dates = [line.strip() for line in f.readlines()]

    available_days = []
    current_date = datetime.date.today() + datetime.timedelta(days=1)

    while len(available_days) < count_days:
        date_str = current_date.strftime("%Y-%m-%d")
        if date_str not in planned_dates:
            available_days.append(date_str)
        current_date += datetime.timedelta(days=1)

    return available_days

# ======================
# PLANLI YÜKLEME
# ======================
def upload_and_schedule(youtube, file_path, publish_time_iso):
    title = os.path.splitext(os.path.basename(file_path))[0]

    body = {
        "snippet": {
            "title": f"{title} #shorts",
            "description": "YT-BatchPilot tarafından otomatik planlanmıştır.",
            "categoryId": "20"
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_time_iso,
            "selfDeclaredMadeForKids": False
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

    print(f"⬆️ Yükleniyor → {publish_time_iso}")
    response = request.execute()
    print(f"✅ Video yüklendi | ID: {response['id']}")

# ======================
# ANA ÇALIŞTIRICI
# ======================
def start_batch_planning():
    youtube = get_youtube_service()

    videos = sorted([
        f for f in os.listdir(INPUT_FOLDER)
        if f.lower().endswith(".mp4")
    ])

    required_videos = len(SCHEDULE_TIMES) * 2
    if len(videos) < required_videos:
        print(f"❌ HATA: En az {required_videos} video olmalı.")
        return

    target_dates = get_next_available_dates(2)
    print(f"📅 Planlanacak günler: {target_dates}")

    video_index = 0

    for date_str in target_dates:
        for time_str in SCHEDULE_TIMES:
            video_file = videos[video_index]
            full_path = os.path.join(INPUT_FOLDER, video_file)
            publish_time = f"{date_str}T{time_str}"

            try:
                upload_and_schedule(youtube, full_path, publish_time)

                shutil.move(
                    full_path,
                    os.path.join(DESTINATION_FOLDER, video_file)
                )

                video_index += 1

            except Exception as e:
                print(f"❌ {video_file} yüklenirken hata oluştu:")
                print(e)
                print("➡️ Diğer videolara devam ediliyor...\n")
                continue

        with open(LOG_FILE, "a") as f:
            f.write(date_str + "\n")

    print("\n🚀 İŞLEM TAMAM")
    print("Planlanabilen tüm videolar başarıyla işlendi.")

# ======================
# ENTRY POINT
# ======================
if __name__ == "__main__":
    start_batch_planning()
