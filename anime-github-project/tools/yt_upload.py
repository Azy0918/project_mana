# -*- coding: utf-8 -*-
"""YouTube 動画アップロード（@yofukashido 用）。OAuth(チャンネル所有者の承認)で投稿する。
事前準備(Google Cloud Console, 1回だけ):
  1. YouTube Data API v3 を有効化
  2. OAuth 同意画面: User type=外部, テストユーザーに自分のGmailを追加, スコープ .../auth/youtube.upload
  3. 認証情報 > OAuthクライアントID > アプリの種類「デスクトップ」を作成 → JSONをDL
  4. そのJSONを tools/yt_client_secret.json として保存
使い方:
  python yt_upload.py --file ../../video/ep01_youtube_vertical_1080x1920.mp4 ^
    --title "深夜二時の第十三レジ 第1話「未来のおにぎり、温めますか」" ^
    --desc "..." --tags "アニメ,紙芝居,SF" --privacy unlisted
初回は run_local_server でブラウザが開き承認 → tools/yt_token.json に保存(以後自動)。
SSL証明書エラーが出る場合は環境変数 MANA_INSECURE_SSL=1 を付けて実行。
"""
import os, sys, argparse
from pathlib import Path
import google.oauth2.credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

TOOLS = Path(__file__).resolve().parent
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET = TOOLS / "yt_client_secret.json"
TOKEN = TOOLS / "yt_token.json"
INSECURE = os.environ.get("MANA_INSECURE_SSL") == "1"


def get_service():
    if not CLIENT_SECRET.exists():
        raise SystemExit(f"OAuthクライアントJSONがありません: {CLIENT_SECRET}\n"
                         "Google CloudでデスクトップOAuthクライアントを作成しDLして上記名で保存してください。")
    creds = None
    if TOKEN.exists():
        creds = google.oauth2.credentials.Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0, prompt="consent")
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    if INSECURE:
        import httplib2
        from google_auth_httplib2 import AuthorizedHttp
        http = AuthorizedHttp(creds, http=httplib2.Http(disable_ssl_certificate_validation=True))
        return build("youtube", "v3", http=http)
    return build("youtube", "v3", credentials=creds)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--desc", default="")
    ap.add_argument("--tags", default="")  # カンマ区切り
    ap.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    ap.add_argument("--category", default="24")  # 24=エンタメ, 1=映画アニメ
    a = ap.parse_args()
    f = Path(a.file)
    if not f.exists():
        raise SystemExit(f"動画が見つかりません: {f}")
    yt = get_service()
    body = {
        "snippet": {"title": a.title, "description": a.desc,
                    "tags": [t.strip() for t in a.tags.split(",") if t.strip()],
                    "categoryId": a.category},
        "status": {"privacyStatus": a.privacy, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(str(f), chunksize=8 * 1024 * 1024, resumable=True, mimetype="video/mp4")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    print(f"アップロード開始: {f.name} ({f.stat().st_size/1_000_000:.1f}MB) privacy={a.privacy}", flush=True)
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"  {int(status.progress()*100)}%", flush=True)
    vid = resp["id"]
    print(f"完了 videoId={vid}\n  視聴: https://youtu.be/{vid}\n  Studio: https://studio.youtube.com/video/{vid}/edit", flush=True)


if __name__ == "__main__":
    main()
