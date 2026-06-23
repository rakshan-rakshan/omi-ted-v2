import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import yt_dlp

t0 = time.time()
ydl = yt_dlp.YoutubeDL({"skip_download": True, "quiet": True, "no_warnings": True})
info = ydl.extract_info("https://www.youtube.com/watch?v=enULurGbDKg", download=False)
print(f"ydl: {time.time()-t0:.1f}s")
print(f"title: {info.get('title', '?')[:50]}")
auto = info.get("automatic_captions") or {}
print(f"auto caps: {list(auto.keys())}")
