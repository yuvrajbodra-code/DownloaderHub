import os, re, uuid, requests, time, hashlib, json, sqlite3
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from flask import Flask, render_template, request, jsonify, send_from_directory
from bs4 import BeautifulSoup
from services.booru_search import (
    validate_booru_tags,
    search_danbooru as booru_search_danbooru,
    search_gelbooru as booru_search_gelbooru,
    fetch_danbooru_tag_suggestions,
    fetch_gelbooru_tag_suggestions
)
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

DATABASE_PATH = "downloader_hub.db"

def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Sync Concurrency Lock
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS x_sync_lock (
        lock_name TEXT PRIMARY KEY,
        locked_at INTEGER NOT NULL
    )
    """)
    
    # Tracked Twitter/X Accounts
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS x_accounts (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        x_user_id TEXT UNIQUE,
        name TEXT,
        profile_image_url TEXT,
        is_active INTEGER NOT NULL DEFAULT 1,
        error_message TEXT,
        last_checked INTEGER,
        last_seen_post_id TEXT,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        deleted_at INTEGER DEFAULT NULL
    )
    """)
    
    # Saved X Posts
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS x_posts (
        id TEXT PRIMARY KEY,
        x_account_id TEXT NOT NULL,
        x_post_id TEXT UNIQUE NOT NULL,
        username TEXT NOT NULL,
        text TEXT NOT NULL,
        post_url TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        saved_at INTEGER NOT NULL,
        raw_json TEXT DEFAULT NULL,
        FOREIGN KEY(x_account_id) REFERENCES x_accounts(id) ON DELETE CASCADE
    )
    """)
    
    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_x_posts_created_at ON x_posts(created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_x_posts_account_created ON x_posts(x_account_id, created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_x_accounts_is_active ON x_accounts(is_active)")
    
    conn.commit()
    conn.close()

# Initialize DB on module load
init_db()

BASE_FOLDER = "downloads"
os.makedirs(BASE_FOLDER, exist_ok=True)

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

progress_store = {}
history_store = {}
downloaded_galleries = {}

# Load existing downloads on startup
def guess_platform_from_folder_name(folder_name):
    lower_name = folder_name.lower()
    if 'pixiv' in lower_name:
        return 'pixiv'
    elif 'deviantart' in lower_name:
        return 'deviantart'
    elif 'imgur' in lower_name:
        return 'imgur'
    elif 'flickr' in lower_name:
        return 'flickr'
    elif 'reddit' in lower_name:
        return 'reddit'
    elif 'tumblr' in lower_name:
        return 'tumblr'
    elif 'twitter' in lower_name or 'x.com' in lower_name:
        return 'twitter'
    elif 'pinterest' in lower_name:
        return 'pinterest'
    elif 'artstation' in lower_name:
        return 'artstation'
    elif re.search(r'-\s*\d+\s*images\s*$', lower_name) or 'imgbox' in lower_name:
        return 'imgbox'
    elif lower_name == 'booru' or 'danbooru' in lower_name or 'gelbooru' in lower_name:
        return 'booru'
    return 'generic'

# ---------- PLATFORM DETECTION ----------
def detect_platform(url):
    """Detect which image hosting platform the URL belongs to"""
    domain = urlparse(url).netloc.lower()
    
    if 'imgbox.com' in domain:
        return 'imgbox'
    elif 'imgur.com' in domain:
        return 'imgur'
    elif 'flickr.com' in domain:
        return 'flickr'
    elif 'pixiv.net' in domain:
        return 'pixiv'
    elif 'danbooru.donmai.us' in domain:
        return 'danbooru'
    elif 'gelbooru.com' in domain:
        return 'gelbooru'
    elif 'deviantart.com' in domain or 'deviantart' in domain:
        return 'deviantart'
    elif 'reddit.com' in domain and ('/r/' in url or '/u/' in url):
        return 'reddit'
    elif 'tumblr.com' in domain:
        return 'tumblr'
    elif 'twitter.com' in domain or 'x.com' in domain:
        return 'twitter'
    elif 'pinterest.com' in domain:
        return 'pinterest'
    elif 'artstation.com' in domain:
        return 'artstation'
    elif 'newgrounds.com' in domain:
        return 'newgrounds'
    else:
        return 'generic'

def get_headers_for_platform(platform, url=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    if platform == 'pixiv':
        headers['Referer'] = 'https://www.pixiv.net/'
    elif platform == 'twitter':
        headers['Referer'] = 'https://x.com/'
    elif platform == 'reddit':
        headers['Referer'] = 'https://www.reddit.com/'
    elif platform == 'danbooru':
        headers['Referer'] = 'https://danbooru.donmai.us/'
    elif platform == 'gelbooru':
        headers['Referer'] = 'https://gelbooru.com/'
    elif url:
        parsed = urlparse(url)
        headers['Referer'] = f"{parsed.scheme}://{parsed.netloc}/"
    return headers

# Load existing downloads on startup
def load_existing_downloads():
    if os.path.exists(BASE_FOLDER):
        for folder_name in os.listdir(BASE_FOLDER):
            folder_path = os.path.join(BASE_FOLDER, folder_name)
            if os.path.isdir(folder_path):
                # Count image files, ignoring metadata.json
                images = [f for f in os.listdir(folder_path) if f.lower().endswith(('.jpg', '.png', '.jpeg', '.gif', '.webp'))]
                image_count = len(images)
                
                # Calculate size in bytes
                folder_size = 0
                try:
                    for f in os.listdir(folder_path):
                        fp = os.path.join(folder_path, f)
                        if os.path.isfile(fp):
                            folder_size += os.path.getsize(fp)
                except:
                    pass
                
                # Check for metadata.json
                metadata_path = os.path.join(folder_path, "metadata.json")
                platform = None
                title = folder_name
                url = None
                
                if os.path.exists(metadata_path):
                    try:
                        with open(metadata_path, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                            platform = meta.get("platform")
                            title = meta.get("title", folder_name)
                            url = meta.get("url")
                    except:
                        pass
                
                # If platform is missing or generic, try to detect from URL
                if url and (not platform or platform == "generic"):
                    detected = detect_platform(url)
                    if detected and detected != "generic":
                        platform = detected
                
                # If still not found, guess from folder name
                if not platform or platform == "generic":
                    platform = guess_platform_from_folder_name(folder_name)
                
                # Always save/update metadata.json to ensure correctness and include url if available
                try:
                    meta_data = {
                        "title": title,
                        "platform": platform,
                        "count": image_count
                    }
                    if url:
                        meta_data["url"] = url
                    with open(metadata_path, "w", encoding="utf-8") as f:
                        json.dump(meta_data, f, ensure_ascii=False, indent=4)
                except:
                    pass
                
                downloaded_galleries[folder_name.lower()] = {
                    "folder": folder_path,
                    "count": image_count,
                    "title": title,
                    "platform": platform,
                    "size_bytes": folder_size
                }

load_existing_downloads()

# ---------- PLATFORM-SPECIFIC EXTRACTORS ----------

# ---------- ORIGINAL WORKING IMGBOX EXTRACTOR ----------
def extract_imgbox_gallery(url, soup):
    """Extract images from Imgbox gallery - ORIGINAL WORKING VERSION"""
    images = []
    
    # Original working method: find all a tags with images
    thumbs = soup.find_all("a", href=True)
    
    for t in thumbs:
        img = t.find("img")
        if not img:
            continue

        src = img.get("src")
        if not src:
            continue

        if "_t." in src:
            full = src.replace("_t.", ".")
        else:
            try:
                page = urljoin(url, t["href"])
                r2 = session.get(page)
                s = BeautifulSoup(r2.content, "html.parser")
                full_img = s.find("img", id="img")
                if full_img:
                    full = urljoin(page, full_img["src"])
                else:
                    continue
            except:
                continue
        
        images.append(full)
    
    return images

def extract_imgur_album(url, soup):
    """Extract images from Imgur album/gallery"""
    images = []
    meta_images = soup.find_all("meta", property="og:image")
    for meta in meta_images:
        img_url = meta.get("content")
        if img_url and 'imgur.com' in img_url:
            img_url = img_url.replace('s.jpg', '.jpg').replace('b.jpg', '.jpg')
            if img_url not in images:
                images.append(img_url)
    img_elements = soup.find_all("img", {"class": re.compile(r".*post-image.*")})
    for img in img_elements:
        src = img.get("src")
        if src and 'imgur.com' in src:
            src = src.replace('s.jpg', '.jpg').replace('b.jpg', '.jpg')
            if src not in images:
                images.append(src)
    scripts = soup.find_all("script")
    for script in scripts:
        if script.string and 'image' in script.string:
            urls = re.findall(r'https?://i\.imgur\.com/[a-zA-Z0-9]+\.\w+', script.string)
            for url in urls:
                if url not in images:
                    images.append(url)
    return images

def extract_flickr_album(url, soup):
    """Extract images from Flickr album"""
    images = []
    img_elements = soup.find_all("img", {"class": re.compile(r".*photo.*")})
    for img in img_elements:
        src = img.get("src")
        if src and 'staticflickr.com' in src:
            src = re.sub(r'_[a-z]\.jpg', '_b.jpg', src)
            images.append(src)
    json_ld = soup.find_all("script", type="application/ld+json")
    for script in json_ld:
        if script.string:
            urls = re.findall(r'https?://live\.staticflickr\.com/[^"\']+\.\w+', script.string)
            images.extend(urls)
    return list(set(images))

def extract_pixiv_artwork(url, soup):
    """Extract images from Pixiv artwork"""
    images = []
    original_links = soup.find_all("a", href=re.compile(r"img-original.*\.(jpg|png|jpeg|gif)"))
    for link in original_links:
        href = link.get("href")
        if href and "img-original" in href:
            if href.startswith("//"):
                href = "https:" + href
            images.append(href)
    if not images:
        img_tags = soup.find_all("img", src=re.compile(r"img-master.*\.(jpg|png|jpeg|gif)"))
        for img in img_tags:
            src = img.get("src")
            if src:
                original = src.replace("img-master", "img-original")
                original = re.sub(r'_master\d+\.', '.', original)
                if original.startswith("//"):
                    original = "https:" + original
                images.append(original)
    if not images:
        img_tags = soup.find_all("img", {"data-src": re.compile(r"img-original|img-master")})
        for img in img_tags:
            src = img.get("data-src") or img.get("src")
            if src:
                if "img-master" in src:
                    original = src.replace("img-master", "img-original")
                    original = re.sub(r'_master\d+\.', '.', original)
                else:
                    original = src
                if original.startswith("//"):
                    original = "https:" + original
                images.append(original)
    seen = set()
    unique_images = []
    for img in images:
        if img not in seen:
            seen.add(img)
            unique_images.append(img)
    return unique_images

def extract_danbooru_post(url, soup):
    images = []
    img_element = soup.find("img", {"id": "image"})
    if img_element:
        src = img_element.get("src")
        if src:
            images.append(src)
    download_link = soup.find("a", {"id": "download-link"})
    if download_link:
        href = download_link.get("href")
        if href:
            images.append(urljoin(url, href))
    return list(set(images))

def extract_gelbooru_post(url, soup):
    images = []
    img_element = soup.find("img", {"id": "image"})
    if img_element:
        src = img_element.get("src")
        if src:
            images.append(src)
    high_res = soup.find("a", {"id": "highres"})
    if high_res:
        href = high_res.get("href")
        if href:
            images.append(urljoin(url, href))
    return list(set(images))

def extract_deviantart_deviation(url, soup):
    images = []
    download_link = soup.find("a", {"class": re.compile(r".*download.*")})
    if download_link:
        href = download_link.get("href")
        if href:
            images.append(href)
    img_element = soup.find("img", {"class": re.compile(r".*deviation-full.*")})
    if img_element:
        src = img_element.get("src")
        if src:
            images.append(src)
    meta_img = soup.find("meta", property="og:image")
    if meta_img:
        img_url = meta_img.get("content")
        if img_url:
            images.append(img_url)
    return list(set(images))

def extract_reddit_gallery(url, soup):
    images = []
    gallery_images = soup.find_all("img", {"class": re.compile(r".*gallery.*")})
    for img in gallery_images:
        src = img.get("src")
        if src and ('i.redd.it' in src or 'preview.redd.it' in src):
            images.append(src)
    main_img = soup.find("img", {"class": re.compile(r".*post-image.*")})
    if main_img:
        src = main_img.get("src")
        if src:
            images.append(src)
    return list(set(images))

def extract_tumblr_post(url, soup):
    images = []
    img_elements = soup.find_all("img", {"class": re.compile(r".*post.*")})
    for img in img_elements:
        src = img.get("src")
        if src and 'media.tumblr.com' in src:
            src = re.sub(r'_\d+\.', '_1280.', src)
            images.append(src)
    return list(set(images))

def extract_twitter_media(url, soup):
    images = []
    img_elements = soup.find_all("img", {"class": re.compile(r".*media.*")})
    for img in img_elements:
        src = img.get("src")
        if src and ('pbs.twimg.com' in src or 'abs.twimg.com' in src):
            src = re.sub(r'&name=\w+', '&name=orig', src)
            images.append(src)
    return list(set(images))

def extract_pinterest_board(url, soup):
    images = []
    img_elements = soup.find_all("img", {"class": re.compile(r".*PinImage.*")})
    for img in img_elements:
        src = img.get("src")
        if src and 'pinimg.com' in src:
            src = re.sub(r'/\d+x/', '/originals/', src)
            images.append(src)
    return list(set(images))

def extract_artstation_project(url, soup):
    images = []
    img_elements = soup.find_all("img", {"class": re.compile(r".*project-image.*")})
    for img in img_elements:
        src = img.get("src")
        if src and 'cdna.artstation.com' in src:
            images.append(src)
    return list(set(images))

def extract_generic_gallery(url, soup):
    images = []
    img_elements = soup.find_all("img")
    for img in img_elements:
        src = img.get("src")
        if src and any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
            full_url = urljoin(url, src)
            if not any(word in src.lower() for word in ['icon', 'logo', 'avatar', 'thumb', 'small', 'avatar', 'icon']):
                images.append(full_url)
    return list(set(images))

# ---------- MAIN EXTRACTOR ----------
def extract_images(url, platform, soup):
    extractors = {
        'imgbox': extract_imgbox_gallery,
        'imgur': extract_imgur_album,
        'flickr': extract_flickr_album,
        'pixiv': extract_pixiv_artwork,
        'danbooru': extract_danbooru_post,
        'gelbooru': extract_gelbooru_post,
        'deviantart': extract_deviantart_deviation,
        'reddit': extract_reddit_gallery,
        'tumblr': extract_tumblr_post,
        'twitter': extract_twitter_media,
        'pinterest': extract_pinterest_board,
        'artstation': extract_artstation_project,
        'generic': extract_generic_gallery
    }
    extractor = extractors.get(platform, extract_generic_gallery)
    return extractor(url, soup)

# ---------- DUPLICATE CHECK ----------
def is_already_downloaded(gallery_title):
    normalized_title = re.sub(r'[\\/:\"*?<>|]+', "_", gallery_title).lower()
    return normalized_title in downloaded_galleries

def get_gallery_info(url):
    try:
        platform = detect_platform(url)
        headers = get_headers_for_platform(platform, url)
        r = session.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.content, "html.parser")
        title = None
        if platform == 'imgbox':
            title_tag = soup.find("h1")
            if title_tag:
                title = title_tag.text.strip()
            else:
                meta_title = soup.find("meta", property="og:title")
                if meta_title:
                    title = meta_title.get("content", "").strip()
                else:
                    title = "Imgbox Gallery"
        elif platform == 'imgur':
            title_tag = soup.find("title")
            title = title_tag.text.strip().replace(" - Imgur", "") if title_tag else "Imgur Album"
        elif platform == 'deviantart':
            title_tag = soup.find("title")
            title = title_tag.text.strip().split(" | ")[0] if title_tag else "DeviantArt"
        else:
            title_tag = soup.find("title")
            if title_tag:
                title = title_tag.text.strip()
                title = re.sub(r'\|.*$', '', title)
                title = re.sub(r'–.*$', '', title)
                title = title.strip()
            else:
                title = f"{platform.capitalize()} Gallery"
        title = re.sub(r'[\\/:\"*?<>|]+', "_", title[:100])
        return {
            "title": title,
            "platform": platform,
            "soup": soup,
            "url": url
        }
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

# ---------- DOWNLOAD ----------
def fetch_image(url, path, gid, platform=None):
    while progress_store[gid]["paused"]:
        time.sleep(0.3)
    if progress_store[gid]["cancelled"]:
        return
    
    headers = get_headers_for_platform(platform or detect_platform(url), url)
    
    max_retries = 3
    for attempt in range(max_retries):
        if progress_store[gid]["cancelled"]:
            return
        try:
            r = session.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                with open(path, "wb") as f:
                    f.write(r.content)
                break
            else:
                print(f"Attempt {attempt+1} failed for {url} with status code: {r.status_code}")
        except Exception as e:
            print(f"Attempt {attempt+1} error downloading {url}: {e}")
        if attempt < max_retries - 1:
            time.sleep(1)
            
    progress_store[gid]["done"] += 1

def download_gallery(url, skip_if_exists=True):
    gid = str(uuid.uuid4())
    progress_store[gid] = {
        "title": "Loading...",
        "platform": "Detecting...",
        "done": 0,
        "total": 0,
        "status": "Fetching",
        "paused": False,
        "cancelled": False
    }
    
    def run_entire_download():
        try:
            gallery_info = get_gallery_info(url)
            if not gallery_info:
                progress_store[gid]["status"] = "Error - Failed to fetch"
                return
            
            title = gallery_info["title"]
            platform = gallery_info["platform"]
            soup = gallery_info["soup"]
            
            progress_store[gid]["title"] = title
            progress_store[gid]["platform"] = platform
            
            if skip_if_exists and is_already_downloaded(title):
                progress_store[gid]["status"] = "Skipped (Already Downloaded)"
                progress_store[gid]["total"] = 0
                def auto_remove():
                    time.sleep(2)
                    if gid in progress_store:
                        del progress_store[gid]
                ThreadPoolExecutor(max_workers=1).submit(auto_remove)
                return
                
            folder = os.path.join(BASE_FOLDER, title)
            os.makedirs(folder, exist_ok=True)
            
            image_urls = extract_images(url, platform, soup)
            if not image_urls:
                progress_store[gid]["status"] = "No images found"
                return
                
            jobs = []
            for idx, img_url in enumerate(image_urls, 1):
                ext = os.path.splitext(img_url.split('?')[0])[1]
                if not ext or len(ext) > 5 or ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']:
                    ext = '.jpg'
                filename = f"{idx:03d}{ext}"
                path = os.path.join(folder, filename)
                jobs.append((img_url, path))
                
            progress_store[gid].update({
                "total": len(jobs),
                "status": "Downloading"
            })
            
            with ThreadPoolExecutor(max_workers=10) as ex:
                futures = [ex.submit(fetch_image, u, p, gid, platform) for u, p in jobs]
                for f in futures:
                    f.result()
                    
            if progress_store[gid]["cancelled"]:
                progress_store[gid]["status"] = "Cancelled"
            else:
                progress_store[gid]["status"] = "Done"
                history_store[gid] = {
                    "title": title,
                    "platform": platform,
                    "count": len(jobs),
                    "folder": folder,
                    "url": url
                }
                
                # Calculate size in bytes
                folder_size = 0
                try:
                    if os.path.isdir(folder):
                        for f in os.listdir(folder):
                            fp = os.path.join(folder, f)
                            if os.path.isfile(fp):
                                folder_size += os.path.getsize(fp)
                except:
                    pass
                    
                downloaded_galleries[title.lower()] = {
                    "folder": folder,
                    "count": len(jobs),
                    "title": title,
                    "platform": platform,
                    "size_bytes": folder_size
                }
                
                # Write metadata.json to persist download information
                try:
                    with open(os.path.join(folder, "metadata.json"), "w", encoding="utf-8") as f:
                        json.dump({
                            "title": title,
                            "platform": platform,
                            "url": url,
                            "count": len(jobs)
                        }, f, ensure_ascii=False, indent=4)
                except Exception as e:
                    print(f"Error writing metadata for {title}: {e}")
        except Exception as e:
            print(f"Error: {e}")
            progress_store[gid]["status"] = "Error"
            
    ThreadPoolExecutor(max_workers=1).submit(run_entire_download)
    return gid

# ---------- ROUTES ----------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/downloads")
def downloads():
    return render_template("index.html")

@app.route("/history")
def history():
    return render_template("index.html")

@app.route("/gallery")
def gallery():
    return render_template("index.html")

@app.route("/sites")
def sites():
    return render_template("index.html")

@app.route("/settings")
def settings():
    return render_template("index.html")

@app.route("/analytics")
def analytics():
    return render_template("index.html")

@app.route("/download", methods=["POST"])
def download():
    data = request.json
    urls_text = data.get("urls", "")
    skip_duplicates = data.get("skip_duplicates", True)
    urls = []
    for part in urls_text.split(','):
        for line in part.split('\n'):
            url = line.strip()
            if url:
                if not url.startswith('http'):
                    url = 'https://' + url
                urls.append(url)
    urls = list(set(urls))
    gids = []
    for url in urls:
        gids.append(download_gallery(url, skip_if_exists=skip_duplicates))
    return jsonify({
        "gids": gids,
        "skipped": [],
        "total": len(gids),
        "skipped_count": 0
    })

@app.route("/control", methods=["POST"])
def control():
    data = request.json
    gid = data.get("id")
    action = data.get("action")
    if gid not in progress_store:
        return jsonify({"ok": False})
    if action == "pause":
        progress_store[gid]["paused"] = True
        progress_store[gid]["status"] = "Paused"
    elif action == "resume":
        progress_store[gid]["paused"] = False
        progress_store[gid]["status"] = "Downloading"
    elif action == "cancel":
        progress_store[gid]["cancelled"] = True
        progress_store[gid]["status"] = "Cancelled"
    elif action == "remove":
        if gid in progress_store:
            del progress_store[gid]
    return jsonify({"ok": True})

@app.route("/status")
def status():
    return jsonify(progress_store)

@app.route("/history-data")
def history_data():
    return jsonify(list(history_store.values()))

@app.route("/downloaded-galleries")
def downloaded_galleries_route():
    return jsonify(list(downloaded_galleries.values()))

@app.route("/stats")
def stats():
    """Return statistics for the dashboard"""
    total_galleries = len(downloaded_galleries)
    total_images = sum(g.get("count", 0) for g in downloaded_galleries.values())
    active_downloads = len([g for g in progress_store.values() if g.get("status") == "Downloading"])
    total_size = sum(g.get("size_bytes", 0) for g in downloaded_galleries.values())
    
    # Platform breakdown
    platforms = {}
    for g in downloaded_galleries.values():
        p = g.get("platform", "generic")
        platforms[p] = platforms.get(p, 0) + 1
    for item in history_store.values():
        p = item.get("platform", "generic")
        if p not in platforms:
            platforms[p] = 0
    return jsonify({
        "total_galleries": total_galleries,
        "total_images": total_images,
        "active_downloads": active_downloads,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 1) if total_size > 0 else 0,
        "platforms": platforms,
        "completed_sessions": len(history_store)
    })

@app.route("/gallery-data")
def gallery_data():
    """Return gallery folders with their images for browsing"""
    galleries = []
    # Build platform lookup from history and downloaded_galleries
    platform_lookup = {}
    for item in history_store.values():
        normalized = item.get("title", "").lower()
        platform_lookup[normalized] = item.get("platform", "generic")
    for key, item in downloaded_galleries.items():
        platform_lookup[key] = item.get("platform", "generic")

    if os.path.exists(BASE_FOLDER):
        for folder_name in sorted(os.listdir(BASE_FOLDER)):
            folder_path = os.path.join(BASE_FOLDER, folder_name)
            if os.path.isdir(folder_path):
                images = sorted([f for f in os.listdir(folder_path) if f.lower().endswith(('.jpg', '.png', '.jpeg', '.gif', '.webp'))])
                if images:
                    cached_info = downloaded_galleries.get(folder_name.lower())
                    if cached_info and "size_bytes" in cached_info:
                        size = cached_info["size_bytes"]
                    else:
                        size = sum(os.path.getsize(os.path.join(folder_path, f)) for f in images)
                    # Get folder creation/modification time
                    try:
                        created_ts = os.path.getctime(folder_path)
                    except:
                        created_ts = 0
                    
                    # Direct check of metadata.json on disk for platform consistency
                    platform = None
                    metadata_path = os.path.join(folder_path, "metadata.json")
                    if os.path.exists(metadata_path):
                        try:
                            with open(metadata_path, "r", encoding="utf-8") as f:
                                meta = json.load(f)
                                platform = meta.get("platform")
                                # If platform is generic but url exists, try to detect platform
                                if (not platform or platform == "generic") and meta.get("url"):
                                    detected = detect_platform(meta.get("url"))
                                    if detected and detected != "generic":
                                        platform = detected
                        except:
                            pass
                    
                    if not platform or platform == "generic":
                        platform = platform_lookup.get(folder_name.lower(), "generic")
                    if not platform or platform == "generic":
                        platform = guess_platform_from_folder_name(folder_name)

                    galleries.append({
                        "title": folder_name,
                        "count": len(images),
                        "size_mb": round(size / (1024*1024), 1),
                        "thumbnail": f"/gallery-image/{folder_name}/{images[0]}",
                        "images": [f"/gallery-image/{folder_name}/{img}" for img in images],
                        "created": created_ts,
                        "platform": platform
                    })
    return jsonify(galleries)

@app.route("/gallery-image/<path:filepath>")
def gallery_image(filepath):
    """Serve gallery images"""
    parts = filepath.split("/", 1)
    if len(parts) == 2:
        return send_from_directory(os.path.join(BASE_FOLDER, parts[0]), parts[1])
    return "", 404

@app.route("/check-duplicates", methods=["POST"])
def check_duplicates():
    data = request.json
    urls = data.get("urls", [])
    results = []
    for url in urls:
        info = get_gallery_info(url)
        if info:
            title = info["title"]
            results.append({
                "url": url,
                "title": title,
                "exists": is_already_downloaded(title),
                "platform": info["platform"]
            })
        else:
            results.append({
                "url": url,
                "title": "Unknown",
                "exists": False,
                "platform": "unknown"
            })
    return jsonify({"results": results})

@app.route("/supported-sites")
def supported_sites():
    sites = {
        "imgbox": {"name": "Imgbox", "desc": "Gallery & image hosting", "color": "#ff6b35", "url": "https://imgbox.com", "domain": "imgbox.com"},
        "imgur": {"name": "Imgur", "desc": "Albums and galleries", "color": "#1bb76e", "url": "https://imgur.com", "domain": "imgur.com"},
        "flickr": {"name": "Flickr", "desc": "Photo albums", "color": "#ff0084", "url": "https://www.flickr.com", "domain": "flickr.com"},
        "pixiv": {"name": "Pixiv", "desc": "Artwork & illustrations", "color": "#0096fa", "url": "https://www.pixiv.net", "domain": "pixiv.net"},
        "danbooru": {"name": "Danbooru", "desc": "Image board posts", "color": "#5b7bd5", "url": "https://danbooru.donmai.us", "domain": "danbooru.donmai.us"},
        "gelbooru": {"name": "Gelbooru", "desc": "Image board posts", "color": "#006ffa", "url": "https://gelbooru.com", "domain": "gelbooru.com"},
        "deviantart": {"name": "DeviantArt", "desc": "Art community", "color": "#05cc47", "url": "https://www.deviantart.com", "domain": "deviantart.com"},
        "reddit": {"name": "Reddit", "desc": "Posts and galleries", "color": "#ff4500", "url": "https://www.reddit.com", "domain": "reddit.com"},
        "tumblr": {"name": "Tumblr", "desc": "Blog posts", "color": "#36465d", "url": "https://www.tumblr.com", "domain": "tumblr.com"},
        "twitter": {"name": "Twitter / X", "desc": "Tweet media", "color": "#1da1f2", "url": "https://x.com", "domain": "x.com"},
        "pinterest": {"name": "Pinterest", "desc": "Pins and boards", "color": "#bd081c", "url": "https://www.pinterest.com", "domain": "pinterest.com"},
        "artstation": {"name": "ArtStation", "desc": "Art projects", "color": "#13aff0", "url": "https://www.artstation.com", "domain": "artstation.com"},
        "generic": {"name": "Generic", "desc": "Any image gallery", "color": "#6c5ce7", "url": "", "domain": ""}
    }
    return jsonify(sites)

@app.route("/delete-gallery", methods=["POST"])
def delete_gallery():
    """Delete a downloaded gallery folder"""
    import shutil
    data = request.json
    title = data.get("title", "")
    folder_path = os.path.join(BASE_FOLDER, title)
    if os.path.isdir(folder_path):
        shutil.rmtree(folder_path)
        normalized = title.lower()
        if normalized in downloaded_galleries:
            del downloaded_galleries[normalized]
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Not found"})

@app.route("/open-folder", methods=["POST"])
def open_folder():
    """Open a gallery folder in Windows File Explorer"""
    data = request.json
    title = data.get("title", "")
    folder_path = os.path.abspath(os.path.join(BASE_FOLDER, title))
    if os.path.isdir(folder_path):
        try:
            os.startfile(folder_path)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})
    return jsonify({"ok": False, "error": "Folder not found"})

def search_danbooru(query):
    results = []
    try:
        url = f"https://danbooru.donmai.us/posts.json?tags={query}&limit=20"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code == 200:
            posts = r.json()
            for post in posts:
                file_url = post.get("file_url")
                preview_url = post.get("preview_file_url") or file_url
                if file_url:
                    results.append({
                        "title": f"Danbooru Post {post.get('id')}",
                        "platform": "danbooru",
                        "thumbnail": preview_url,
                        "url": file_url,
                        "post_url": f"https://danbooru.donmai.us/posts/{post.get('id')}",
                        "tags": post.get("tag_string", "")[:200]
                    })
    except Exception as e:
        print(f"Danbooru search error: {e}")
    return results

def search_gelbooru(query):
    results = []
    try:
        url = f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&tags={query}&limit=20"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code == 200:
            data = r.json()
            posts = data.get("post", [])
            for post in posts:
                file_url = post.get("file_url")
                preview_url = post.get("preview_url") or file_url
                if file_url:
                    results.append({
                        "title": f"Gelbooru Post {post.get('id')}",
                        "platform": "gelbooru",
                        "thumbnail": preview_url,
                        "url": file_url,
                        "post_url": f"https://gelbooru.com/index.php?page=post&s=view&id={post.get('id')}",
                        "tags": post.get("tags", "")[:200]
                    })
    except Exception as e:
        print(f"Gelbooru search error: {e}")
    return results

def search_reddit(query):
    results = []
    try:
        url = f"https://www.reddit.com/search.json?q={query}&limit=20"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code == 200:
            data = r.json()
            posts = data.get("data", {}).get("children", [])
            for post in posts:
                pdata = post.get("data", {})
                img_url = pdata.get("url", "")
                is_image = any(img_url.lower().endswith(ext) for ext in ['.jpg', '.png', '.jpeg', '.gif', '.webp'])
                preview = img_url
                if not is_image:
                    previews = pdata.get("preview", {}).get("images", [])
                    if previews:
                        source = previews[0].get("source", {})
                        if source.get("url"):
                            preview = source.get("url").replace("&amp;", "&")
                            is_image = True
                
                if is_image:
                    results.append({
                        "title": pdata.get("title", "Reddit Post"),
                        "platform": "reddit",
                        "thumbnail": preview,
                        "url": img_url,
                        "post_url": f"https://www.reddit.com{pdata.get('permalink')}",
                        "tags": f"r/{pdata.get('subreddit')}"
                    })
    except Exception as e:
        print(f"Reddit search error: {e}")
    return results

def check_deviantart_updates(username):
    import xml.etree.ElementTree as ET
    urls = []
    try:
        url = f"https://backend.deviantart.com/rss.html?q=gallery:{username}"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            for item in root.findall(".//item"):
                link = item.find("link")
                if link is not None and link.text:
                    urls.append(link.text)
    except Exception as e:
        print(f"DeviantArt subscription update error: {e}")
    return urls

def check_reddit_updates(subreddit_name):
    urls = []
    try:
        if subreddit_name.startswith("user/"):
            url = f"https://www.reddit.com/{subreddit_name}/submitted.json?limit=25"
        else:
            sub = subreddit_name.replace("r/", "").strip()
            url = f"https://www.reddit.com/r/{sub}/new.json?limit=25"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            posts = data.get("data", {}).get("children", [])
            for post in posts:
                permalink = post.get("data", {}).get("permalink")
                if permalink:
                    urls.append(f"https://www.reddit.com{permalink}")
    except Exception as e:
        print(f"Reddit subscription update error: {e}")
    return urls

def check_danbooru_updates(tags):
    urls = []
    try:
        url = f"https://danbooru.donmai.us/posts.json?tags={tags}&limit=20"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            posts = r.json()
            for post in posts:
                post_id = post.get("id")
                if post_id:
                    urls.append(f"https://danbooru.donmai.us/posts/{post_id}")
    except Exception as e:
        print(f"Danbooru subscription update error: {e}")
    return urls

def check_gelbooru_updates(tags):
    urls = []
    try:
        url = f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&tags={tags}&limit=20"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            posts = data.get("post", [])
            for post in posts:
                post_id = post.get("id")
                if post_id:
                    urls.append(f"https://gelbooru.com/index.php?page=post&s=view&id={post_id}")
    except Exception as e:
        print(f"Gelbooru subscription update error: {e}")
    return urls

SUBS_FILE = "subscriptions.json"

def load_subscriptions():
    if os.path.exists(SUBS_FILE):
        try:
            with open(SUBS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []

def save_subscriptions(subs):
    try:
        with open(SUBS_FILE, "w", encoding="utf-8") as f:
            json.dump(subs, f, ensure_ascii=False, indent=4)
        return True
    except:
        return False

@app.route("/api/discover")
def api_discover():
    query = request.args.get("q", "").strip()
    platforms_str = request.args.get("platforms", "danbooru,gelbooru,reddit")
    platforms = [p.strip().lower() for p in platforms_str.split(",") if p.strip()]
    
    if not query:
        return jsonify([])
        
    results = []
    jobs = []
    
    with ThreadPoolExecutor(max_workers=5) as ex:
        if "danbooru" in platforms:
            jobs.append(ex.submit(search_danbooru, query))
        if "gelbooru" in platforms:
            jobs.append(ex.submit(search_gelbooru, query))
        if "reddit" in platforms:
            jobs.append(ex.submit(search_reddit, query))
            
        for f in jobs:
            results.extend(f.result())
            
    return jsonify(results)

# --- BOORU EXPLORER ENDPOINT ---

DISCOVER_CACHE = {}
RATE_LIMIT_STORE = {}
TAG_SUGGESTIONS_CACHE = {}
TAG_LIMIT_STORE = {}

def parse_date_to_timestamp(date_str):
    if not date_str:
        return 0
    date_str = str(date_str).strip()
    try:
        temp = date_str.replace('Z', '+00:00')
        import datetime
        return datetime.datetime.fromisoformat(temp).timestamp()
    except Exception:
        pass
    try:
        import datetime
        return datetime.datetime.strptime(date_str, "%a %b %d %H:%M:%S %z %Y").timestamp()
    except Exception:
        pass
    return 0

@app.route("/api/discover/booru-search")
def api_discover_booru_search():
    # 1. IP-based Rate Limiting (15 req/min)
    ip = request.remote_addr
    now = time.time()
    if ip not in RATE_LIMIT_STORE:
        RATE_LIMIT_STORE[ip] = []
    
    # Filter timestamps older than 60s
    RATE_LIMIT_STORE[ip] = [t for t in RATE_LIMIT_STORE[ip] if now - t < 60]
    
    if len(RATE_LIMIT_STORE[ip]) >= 15:
        return jsonify({
            "error": True,
            "message": "Too many requests. Please wait a moment before searching again."
        }), 429
        
    RATE_LIMIT_STORE[ip].append(now)

    # 2. Input Parameter Parsing & Validation
    q = request.args.get("q", "")
    if not q:
        return jsonify({
            "error": True,
            "message": "Query parameter 'q' is required."
        }), 400
        
    safe_mode_param = request.args.get("safe_mode", "true").lower()
    safe_mode = safe_mode_param in ("true", "1")

    try:
        q_cleaned = validate_booru_tags(q)
    except ValueError as e:
        return jsonify({
            "error": True,
            "message": str(e)
        }), 400

    # Strip custom rating tags at route level to enforce safe search only if safe_mode is active
    tags_list = [t for t in q_cleaned.split(' ') if t.strip()]
    if safe_mode:
        cleaned_tags_list = [t for t in tags_list if not t.lower().startswith("rating:")]
    else:
        cleaned_tags_list = tags_list

    if not cleaned_tags_list:
        return jsonify({
            "error": True,
            "message": "Search query must contain at least one valid search tag."
        }), 400
    q_cleaned = " ".join(cleaned_tags_list)
        
    sources_str = request.args.get("sources", "danbooru,gelbooru")
    sources = [s.strip().lower() for s in sources_str.split(",") if s.strip()]
    if not sources:
        sources = ["danbooru", "gelbooru"]
        
    for s in sources:
        if s not in ("danbooru", "gelbooru"):
            return jsonify({
                "error": True,
                "message": f"Invalid source '{s}' requested. Only 'danbooru' and 'gelbooru' are supported."
            }), 400
            
    page_str = request.args.get("page", "1")
    try:
        page = int(page_str)
        if page < 1:
            raise ValueError()
    except ValueError:
        return jsonify({
            "error": True,
            "message": "Parameter 'page' must be a positive integer."
        }), 400
        
    limit_str = request.args.get("limit", "20")
    try:
        limit = int(limit_str)
    except ValueError:
        limit = 20
    limit = min(max(1, limit), 24)

    # 3. Cache Lookup
    normalized_q = " ".join(sorted(q_cleaned.split()))
    normalized_sources = ",".join(sorted(sources))
    cache_key = (normalized_q, normalized_sources, page, limit, safe_mode)
    
    cached_entry = DISCOVER_CACHE.get(cache_key)
    if cached_entry:
        cache_time, response_data, is_error = cached_entry
        ttl = 15 if is_error else 120
        if now - cache_time < ttl:
            return jsonify(response_data)
        else:
            del DISCOVER_CACHE[cache_key]

    # 4. Concurrent Query Execution
    results = []
    errors = []
    has_more = {}
    
    jobs = {}
    with ThreadPoolExecutor(max_workers=2) as ex:
        if "danbooru" in sources:
            jobs["danbooru"] = ex.submit(booru_search_danbooru, q_cleaned, page, limit, safe_mode)
        if "gelbooru" in sources:
            jobs["gelbooru"] = ex.submit(booru_search_gelbooru, q_cleaned, page, limit, safe_mode)
            
        for src, fut in jobs.items():
            try:
                res = fut.result()
                if res.get("error"):
                    errors.append({
                        "source": src,
                        "message": res.get("message")
                    })
                    has_more[src] = False
                else:
                    results.extend(res.get("results", []))
                    has_more[src] = res.get("has_more", False)
            except Exception as e:
                errors.append({
                    "source": src,
                    "message": "Service encountered an error."
                })
                has_more[src] = False

    # 5. Deduplication by (source, post_id)
    seen = set()
    deduped_results = []
    for r in results:
        key = (r.get("source"), r.get("post_id"))
        if key not in seen:
            seen.add(key)
            deduped_results.append(r)

    # 6. Sorting (newest first)
    deduped_results.sort(key=lambda x: parse_date_to_timestamp(x.get("created_at")), reverse=True)

    # Limit total unified results to 48 maximum
    final_results = deduped_results[:48]

    # 7. Construct Response
    response_payload = {
        "query": q_cleaned,
        "sources": sources,
        "page": page,
        "safe_mode": safe_mode,
        "results": final_results,
        "errors": errors,
        "has_more": has_more
    }

    # 8. Cache Writing
    has_any_errors = len(errors) > 0
    DISCOVER_CACHE[cache_key] = (now, response_payload, has_any_errors)

    return jsonify(response_payload)

@app.route("/api/discover/save-to-gallery", methods=["POST"])
def api_discover_save_to_gallery():
    """Download a booru post image to the local gallery.
    
    Tries original_url first. If the CDN returns 403/404 (common for Gelbooru
    full-res images that require cookies), falls back to display_url (the
    sample/preview, which is the same URL that the in-site proxy-image already
    serves successfully).
    """
    data = request.get_json(silent=True) or {}
    original_url = data.get("original_url", "").strip()
    display_url  = data.get("display_url", "").strip()   # fallback sample URL
    source   = data.get("source", "").strip().lower()    # 'danbooru' or 'gelbooru'
    post_id  = str(data.get("post_id", "")).strip()

    if not original_url and not display_url:
        return jsonify({"ok": False, "error": "Missing image URL"}), 400
    if source not in ("danbooru", "gelbooru"):
        return jsonify({"ok": False, "error": "Unsupported source"}), 400
    if not post_id:
        return jsonify({"ok": False, "error": "Missing post_id"}), 400

    # Full browser-like headers — Gelbooru CDN checks these
    def _build_headers(img_url):
        parsed = urlparse(img_url)
        # Always use the booru root as Referer, not the CDN sub-domain
        if source == "gelbooru" or "gelbooru.com" in parsed.netloc:
            referer = "https://gelbooru.com/"
        elif source == "danbooru" or "donmai.us" in parsed.netloc:
            referer = "https://danbooru.donmai.us/"
        else:
            referer = f"{parsed.scheme}://{parsed.netloc}/"

        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Referer": referer,
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Fetch-Dest": "image",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "cross-site",
            "Cache-Control": "no-cache",
        }

    def _try_download(img_url):
        """Return (content_bytes, ext) or raise on error."""
        headers = _build_headers(img_url)
        r = requests.get(img_url, headers=headers, timeout=30, stream=True)
        if r.status_code != 200:
            raise ValueError(f"HTTP {r.status_code}")
        content = r.content
        url_path = urlparse(img_url).path
        ext = os.path.splitext(url_path)[1].lower()
        if not ext or ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.avif'):
            # Try Content-Type header
            ct = r.headers.get("Content-Type", "")
            ext_map = {"jpeg": ".jpg", "jpg": ".jpg", "png": ".png",
                       "gif": ".gif", "webp": ".webp", "avif": ".avif"}
            for k, v in ext_map.items():
                if k in ct:
                    ext = v
                    break
            else:
                ext = ".jpg"
        return content, ext

    # Build gallery folder
    booru_folder = os.path.join(BASE_FOLDER, "Booru")
    os.makedirs(booru_folder, exist_ok=True)

    # --- Try original_url, then fall back to display_url ---
    content = None
    ext = ".jpg"
    used_url = original_url or display_url
    urls_to_try = []
    if original_url:
        urls_to_try.append(("original", original_url))
    if display_url and display_url != original_url:
        urls_to_try.append(("display", display_url))

    last_error = "No URLs to try"
    for url_label, try_url in urls_to_try:
        try:
            content, ext = _try_download(try_url)
            used_url = try_url
            print(f"[save-to-gallery] Downloaded {source}/{post_id} via {url_label} URL")
            break
        except Exception as e:
            last_error = str(e)
            print(f"[save-to-gallery] {url_label} URL failed for {source}/{post_id}: {e}")

    if content is None:
        return jsonify({"ok": False, "error": f"Could not download image: {last_error}"}), 502

    filename = f"{source}_{post_id}{ext}"
    filepath = os.path.join(booru_folder, filename)

    # Skip write if already saved (check after resolving extension)
    if os.path.exists(filepath):
        _refresh_booru_gallery_entry(booru_folder)
        return jsonify({"ok": True, "filename": filename, "already_existed": True})

    try:
        with open(filepath, "wb") as f:
            f.write(content)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to write file: {e}"}), 500

    _refresh_booru_gallery_entry(booru_folder)
    return jsonify({"ok": True, "filename": filename, "already_existed": False})


def _refresh_booru_gallery_entry(booru_folder):
    """Recount files in the Booru gallery folder and update downloaded_galleries."""
    try:
        images = [f for f in os.listdir(booru_folder)
                  if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.avif'))]
        folder_size = sum(
            os.path.getsize(os.path.join(booru_folder, f))
            for f in images
            if os.path.isfile(os.path.join(booru_folder, f))
        )
        key = "booru"
        downloaded_galleries[key] = {
            "folder": booru_folder,
            "count": len(images),
            "title": "Booru",
            "platform": "booru",
            "size_bytes": folder_size
        }
        # Write / refresh metadata.json
        meta_path = os.path.join(booru_folder, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as mf:
            json.dump({"title": "Booru", "platform": "booru", "count": len(images)}, mf, indent=4)
    except Exception as e:
        print(f"Error refreshing booru gallery entry: {e}")


@app.route("/api/proxy-image")
def proxy_image():
    url = request.args.get("url")
    if not url:
        return "Missing url parameter", 400
        
    parsed = urlparse(url)
    allowed_domains = ("gelbooru.com", "donmai.us", "staticflickr.com", "pinimg.com")
    if not parsed.netloc or not any(domain in parsed.netloc.lower() for domain in allowed_domains):
        return "Forbidden domain", 403
        
    try:
        referer = f"{parsed.scheme}://{parsed.netloc}/"
        if "gelbooru.com" in parsed.netloc.lower():
            referer = "https://gelbooru.com/"
            
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": referer
        }
        
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            from flask import Response
            return Response(r.content, mimetype=r.headers.get("Content-Type", "image/jpeg"))
        else:
            return f"Failed to fetch image: status code {r.status_code}", 502
    except Exception as e:
        return f"Error proxying image: {str(e)}", 500

@app.route("/api/discover/tag-suggestions")
def api_discover_tag_suggestions():
    # 1. IP-based Rate Limiting (60 req/min)
    ip = request.remote_addr
    now = time.time()
    if ip not in TAG_LIMIT_STORE:
        TAG_LIMIT_STORE[ip] = []
    
    # Filter timestamps older than 60s
    TAG_LIMIT_STORE[ip] = [t for t in TAG_LIMIT_STORE[ip] if now - t < 60]
    
    if len(TAG_LIMIT_STORE[ip]) >= 60:
        return jsonify({
            "error": True,
            "message": "Too many requests. Please wait a moment before trying again."
        }), 429
        
    TAG_LIMIT_STORE[ip].append(now)

    # 2. Input Parameter Parsing & Extraction
    q = request.args.get("q", "")
    sources_str = request.args.get("sources", "danbooru,gelbooru")
    sources = [s.strip().lower() for s in sources_str.split(",") if s.strip()]
    if not sources:
        sources = ["danbooru", "gelbooru"]

    # Validate sources
    for s in sources:
        if s not in ("danbooru", "gelbooru"):
            return jsonify({
                "error": True,
                "message": f"Invalid source '{s}' requested. Only 'danbooru' and 'gelbooru' are supported."
            }), 400

    # Extract final token and prefix
    active_token = ""
    prefix = ""
    if q:
        last_space_idx = q.rfind(" ")
        if last_space_idx == -1:
            active_token = q
            prefix = ""
        else:
            active_token = q[last_space_idx + 1:]
            prefix = q[:last_space_idx + 1]

    # 3. Check Ignore Autocomplete rules
    metatags = ("rating:", "order:", "score:", "id:", "date:", "user:", "pool:", "fav:", "source:", "parent:")
    
    ignore = False
    if not q:
        ignore = True
    elif len(active_token) < 2:
        ignore = True
    elif active_token.startswith("-"):
        ignore = True
    elif not re.match(r'^[a-zA-Z0-9_\-:\(\)]+$', active_token):
        ignore = True
    elif any(active_token.lower().startswith(m) for m in metatags):
        ignore = True

    if ignore:
        return jsonify({
            "active_token": active_token,
            "prefix": prefix,
            "suggestions": []
        })

    # 4. Cache Lookup
    cache_key = (active_token.lower(), tuple(sorted(sources)))
    cached_entry = TAG_SUGGESTIONS_CACHE.get(cache_key)
    if cached_entry:
        cache_time, response_payload = cached_entry
        if now - cache_time < 300: # 5 minutes
            return jsonify(response_payload)
        else:
            del TAG_SUGGESTIONS_CACHE[cache_key]

    # 5. Concurrent Fetching
    danbooru_sug = []
    gelbooru_sug = []
    
    with ThreadPoolExecutor(max_workers=2) as ex:
        jobs = {}
        if "danbooru" in sources:
            jobs["danbooru"] = ex.submit(fetch_danbooru_tag_suggestions, active_token)
        if "gelbooru" in sources:
            jobs["gelbooru"] = ex.submit(fetch_gelbooru_tag_suggestions, active_token)
            
        for src, fut in jobs.items():
            try:
                res = fut.result()
                if src == "danbooru":
                    danbooru_sug = res
                elif src == "gelbooru":
                    gelbooru_sug = res
            except Exception:
                pass

    # 6. Deduplication and Merging
    merged = {}
    for item in danbooru_sug:
        tag_name = item["tag"]
        if tag_name not in merged:
            merged[tag_name] = {
                "tag": tag_name,
                "label": item["label"],
                "category": item["category"],
                "post_count": item["post_count"],
                "sources": [item["source"]]
            }

    for item in gelbooru_sug:
        tag_name = item["tag"]
        if tag_name in merged:
            if item["source"] not in merged[tag_name]["sources"]:
                merged[tag_name]["sources"].append(item["source"])
            merged[tag_name]["post_count"] = max(merged[tag_name]["post_count"], item["post_count"])
        else:
            merged[tag_name] = {
                "tag": tag_name,
                "label": item["label"],
                "category": item["category"],
                "post_count": item["post_count"],
                "sources": [item["source"]]
            }

    # Convert to list and sort
    suggestions_list = list(merged.values())
    suggestions_list.sort(key=lambda x: (
        not x["tag"].lower().startswith(active_token.lower()),
        -x["post_count"],
        x["tag"].lower()
    ))

    # Limit to 12 suggestions
    final_suggestions = suggestions_list[:12]

    # Construct response
    response_payload = {
        "active_token": active_token,
        "prefix": prefix,
        "suggestions": final_suggestions
    }

    # 7. Write to cache
    TAG_SUGGESTIONS_CACHE[cache_key] = (now, response_payload)

    return jsonify(response_payload)

@app.route("/api/subscriptions")
def api_get_subscriptions():
    return jsonify(load_subscriptions())

@app.route("/api/subscriptions/add", methods=["POST"])
def api_add_subscription():
    data = request.json
    name = data.get("name", "").strip()
    url = data.get("url", "").strip()
    
    if not name or not url:
        return jsonify({"ok": False, "error": "Name and URL are required"})
        
    platform = detect_platform(url)
    if platform == "generic" and ("deviantart.com" in url or "deviantart" in url):
        platform = "deviantart"
        
    subs = load_subscriptions()
    for s in subs:
        if s["url"].lower() == url.lower():
            return jsonify({"ok": False, "error": "Already subscribed to this URL"})
            
    new_sub = {
        "id": str(uuid.uuid4()),
        "name": name,
        "url": url,
        "platform": platform,
        "last_checked": None,
        "downloaded_count": 0
    }
    subs.append(new_sub)
    save_subscriptions(subs)
    return jsonify({"ok": True, "subscription": new_sub})

@app.route("/api/subscriptions/delete", methods=["POST"])
def api_delete_subscription():
    data = request.json
    sub_id = data.get("id")
    
    subs = load_subscriptions()
    updated_subs = [s for s in subs if s["id"] != sub_id]
    
    if len(subs) == len(updated_subs):
        return jsonify({"ok": False, "error": "Subscription not found"})
        
    save_subscriptions(updated_subs)
    return jsonify({"ok": True})

@app.route("/api/subscriptions/update", methods=["POST"])
def api_update_subscriptions():
    data = request.json
    sub_id = data.get("id")
    
    subs = load_subscriptions()
    
    def run_update():
        for s in subs:
            if sub_id and s["id"] != sub_id:
                continue
                
            platform = s["platform"]
            url = s["url"]
            
            feed_urls = []
            if platform == "reddit":
                if "/r/" in url:
                    sub_name = url.split("/r/")[1].split("/")[0]
                    feed_urls = check_reddit_updates("r/" + sub_name)
                elif "/user/" in url or "/u/" in url:
                    user_part = url.split("/user/") if "/user/" in url else url.split("/u/")
                    user_name = user_part[1].split("/")[0]
                    feed_urls = check_reddit_updates("user/" + user_name)
            elif platform == "deviantart":
                parsed = urlparse(url)
                username = None
                if "deviantart.com" in parsed.netloc:
                    parts = parsed.netloc.split(".")
                    if len(parts) > 2:
                        username = parts[0]
                if not username:
                    path_parts = parsed.path.strip("/").split("/")
                    if path_parts:
                        username = path_parts[0]
                if username:
                    feed_urls = check_deviantart_updates(username)
            elif platform == "danbooru":
                parsed = urlparse(url)
                query_params = dict(part.split("=") for part in parsed.query.split("&") if "=" in part)
                tags = query_params.get("tags")
                if tags:
                    feed_urls = check_danbooru_updates(tags)
            elif platform == "gelbooru":
                parsed = urlparse(url)
                query_params = dict(part.split("=") for part in parsed.query.split("&") if "=" in part)
                tags = query_params.get("tags")
                if tags:
                    feed_urls = check_gelbooru_updates(tags)
                    
            triggered_count = 0
            for feed_url in feed_urls:
                info = get_gallery_info(feed_url)
                if info:
                    title = info["title"]
                    if not is_already_downloaded(title):
                        download_gallery(feed_url, skip_if_exists=True)
                        triggered_count += 1
                        
            s["last_checked"] = int(time.time())
            s["downloaded_count"] = s.get("downloaded_count", 0) + triggered_count
            
        save_subscriptions(subs)
        
    ThreadPoolExecutor(max_workers=1).submit(run_update)
    return jsonify({"ok": True, "message": "Updates checked in background"})

# Route handlers to render templates for sub pages so directly accessing /discover or /subscriptions works
@app.route("/discover")
def discover():
    return render_template("index.html")

@app.route("/subscriptions")
def subscriptions_route():
    return render_template("index.html")

if __name__ == "__main__":
    if not os.environ.get("GELBOORU_USER_ID") or not os.environ.get("GELBOORU_API_KEY"):
        print("\n" + "="*80)
        print(" WARNING: Gelbooru authentication credentials are missing!")
        print(" Please define GELBOORU_USER_ID and GELBOORU_API_KEY in your environment/.env file.")
        print(" Gelbooru discover searches will be disabled until these are set.")
        print("="*80 + "\n")
    app.run(debug=True)