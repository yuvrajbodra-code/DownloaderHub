import os, re
import requests
from urllib.parse import urlparse

# Project Constants
USER_AGENT = "Downloader Hub/3.0 (Booru Explorer Search Module)"
TIMEOUT = (3.0, 6.0)  # Connect timeout, Read timeout

def validate_booru_tags(query: str) -> str:
    """
    Trims, collapses whitespace, validates, and cleans the query string.
    Raises ValueError if validation fails.
    """
    if not query:
        raise ValueError("Search query cannot be empty.")
    
    # Reject newlines and carriage returns explicitly
    if "\n" in query or "\r" in query:
        raise ValueError("Search query cannot contain newlines.")
    
    # Reject control chars, null bytes
    if re.search(r'[\x00-\x1f\x7f-\x9f]', query):
        raise ValueError("Search query contains invalid control characters.")
        
    # Trim and collapse spaces
    cleaned = query.strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    # Length validation
    if not (1 <= len(cleaned) <= 200):
        raise ValueError("Search query must be between 1 and 200 characters.")
    
    # Reject HTML fragments
    if "<" in cleaned or ">" in cleaned or "&" in cleaned:
        raise ValueError("Search query contains invalid characters (<, >, &).")
    
    # Reject URLs / protocols
    if re.search(r'(https?|ftp|file)://', cleaned, re.IGNORECASE):
        raise ValueError("Search query cannot contain URLs.")
        
    # Allow normal booru tag syntax: letters, numbers, underscores, hyphens, colons, parentheses, and spaces.
    # Regex checks if the entire string consists only of allowed characters
    if not re.match(r'^[a-zA-Z0-9_\-:\(\) ]+$', cleaned):
        raise ValueError("Search query contains unsupported characters. Only alphanumeric, spaces, and _ - : ( ) are allowed.")
        
    return cleaned

def sanitize_tag_list(tag_data, limit_count: int = 50) -> list:
    """
    Normalizes tag string or list into a clean list of strings, up to a limit.
    """
    if not tag_data:
        return []
    if isinstance(tag_data, str):
        tags = [t.strip().lower() for t in tag_data.split(' ') if t.strip()]
    elif isinstance(tag_data, list):
        tags = [str(t).strip().lower() for t in tag_data if str(t).strip()]
    else:
        return []
    return tags[:limit_count]

def normalize_rating(rating_str: str) -> str:
    """
    Maps upstream rating chars/words to 'safe', 'questionable', or 'explicit'.
    """
    if not rating_str:
        return "safe"
    r = rating_str.lower().strip()
    if r in ('g', 'general', 's', 'sensitive', 'safe'):
        return "safe"
    if r in ('q', 'questionable'):
        return "questionable"
    if r in ('e', 'explicit'):
        return "explicit"
    return "safe"

def safe_external_image_url(url: str) -> str:
    """
    Validates that the external URL is an http/https link with a safe structure.
    Returns the URL if safe, or empty string.
    """
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        if parsed.scheme in ('http', 'https') and parsed.netloc:
            # Basic domain hygiene - prevent arbitrary loopback or localhost queries
            if parsed.netloc.lower() in ('localhost', '127.0.0.1', '0.0.0.0'):
                return ""
            return url
    except Exception:
        pass
    return ""

def make_provider_error(provider: str, message: str) -> dict:
    """
    Standardizes error payloads.
    """
    return {
        "error": True,
        "provider": provider,
        "message": message,
        "results": [],
        "has_more": False
    }

def clean_tags_for_safe_search(tags_str: str) -> list:
    """
    Parses and removes any custom rating tags requested by user to enforce safe mode.
    """
    tags = sanitize_tag_list(tags_str)
    # Filter out any user rating query
    cleaned_tags = [t for t in tags if not t.startswith("rating:")]
    return cleaned_tags

def search_danbooru(tags_str: str, page: int = 1, limit: int = 20, safe_mode: bool = True) -> dict:
    """
    Search Danbooru JSON API. Safe ratings are optionally enforced.
    """
    provider = "danbooru"
    page = max(1, page)
    limit = min(max(1, limit), 24)
    
    try:
        if safe_mode:
            cleaned_tags = clean_tags_for_safe_search(tags_str)
            
            # Danbooru limits search to 2 tags for anonymous queries.
            # If we have 0 or 1 tag, we append rating:g to be extra safe at request level.
            # If we have 2 or more tags, appending rating:g would trigger a 422 limit error,
            # so we query tags as-is and filter strictly post-fetch.
            if len(cleaned_tags) <= 1:
                query_tags = cleaned_tags + ["rating:g"]
            else:
                query_tags = cleaned_tags
        else:
            query_tags = sanitize_tag_list(tags_str)
            
        params = {
            "tags": " ".join(query_tags),
            "page": page,
            "limit": limit
        }
        
        headers = {
            "User-Agent": USER_AGENT
        }
        
        url = "https://danbooru.donmai.us/posts.json"
        
        r = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
        
        if r.status_code == 429:
            return make_provider_error(provider, "Too many requests. Please try again later.")
        if r.status_code != 200:
            return make_provider_error(provider, f"Danbooru API returned status code {r.status_code}")
            
        posts = r.json()
        if not isinstance(posts, list):
            return make_provider_error(provider, "Invalid response format received from Danbooru.")
            
        normalized_results = []
        for post in posts:
            # Skip if post dict is invalid or empty
            if not isinstance(post, dict):
                continue
                
            # Filter deleted, banned, or posts without files
            if post.get("is_deleted") or post.get("is_banned"):
                continue
                
            # Upstream rating check - strictly keep only 'g' (general) or 's' (sensitive) if safe_mode is active.
            # Questionable and Explicit are strictly omitted under safe_mode.
            upstream_rating = post.get("rating")
            if safe_mode and upstream_rating not in ("g", "s"):
                continue
                
            post_id = post.get("id")
            if not post_id:
                continue
                
            # Select preview thumbnail
            preview_url = post.get("preview_file_url") or post.get("large_file_url") or post.get("file_url")
            if not preview_url:
                continue
                
            normalized_results.append({
                "source": provider,
                "source_label": "Danbooru",
                "post_id": str(post_id),
                "post_url": f"https://danbooru.donmai.us/posts/{post_id}",
                "preview_url": safe_external_image_url(preview_url),
                "sample_url": safe_external_image_url(post.get("large_file_url")),
                "file_url": safe_external_image_url(post.get("file_url")),
                "thumbnail_url": safe_external_image_url(preview_url),
                "display_url": safe_external_image_url(post.get("large_file_url") or post.get("file_url") or preview_url),
                "original_url": safe_external_image_url(post.get("file_url")),
                "width": int(post.get("image_width") or 0),
                "height": int(post.get("image_height") or 0),
                "rating": normalize_rating(upstream_rating),
                "score": int(post.get("score") or 0),
                "created_at": post.get("created_at"),
                "tags": sanitize_tag_list(post.get("tag_string")),
                "artist_tags": sanitize_tag_list(post.get("tag_string_artist")),
                "character_tags": sanitize_tag_list(post.get("tag_string_character")),
                "copyright_tags": sanitize_tag_list(post.get("tag_string_copyright"))
            })
            
        return {
            "error": False,
            "provider": provider,
            "results": normalized_results,
            "has_more": len(posts) >= limit
        }
        
    except requests.exceptions.Timeout:
        return make_provider_error(provider, "Connection timed out.")
    except Exception as e:
        # Avoid sharing stack trace in the message, keep it clean
        return make_provider_error(provider, "Search failed due to a system error.")

def search_gelbooru(tags_str: str, page: int = 1, limit: int = 20, safe_mode: bool = True) -> dict:
    """
    Search Gelbooru JSON API with credentials. Safe ratings are optionally enforced.
    """
    provider = "gelbooru"
    page = max(1, page)
    limit = min(max(1, limit), 24)
    
    # 1. Load dotenv dynamically and check for configured Gelbooru credentials
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    user_id = os.environ.get("GELBOORU_USER_ID")
    api_key = os.environ.get("GELBOORU_API_KEY")
    if not user_id or not api_key:
        return make_provider_error(
            provider, 
            "Gelbooru is not configured. Add GELBOORU_USER_ID and GELBOORU_API_KEY on the server."
        )
    
    try:
        if safe_mode:
            cleaned_tags = clean_tags_for_safe_search(tags_str)
            # Gelbooru does not have a 2-tag search limit for anonymous queries.
            # We append 'rating:general' to filter safe posts at query level.
            query_tags = cleaned_tags + ["rating:general"]
        else:
            query_tags = sanitize_tag_list(tags_str)
        
        params = {
            "page": "dapi",
            "s": "post",
            "q": "index",
            "json": 1,
            "api_key": api_key,
            "user_id": user_id,
            "tags": " ".join(query_tags),
            "pid": page - 1,  # Gelbooru page starts at 0
            "limit": limit
        }
        
        headers = {
            "User-Agent": USER_AGENT
        }
        
        url = "https://gelbooru.com/index.php"
        
        r = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
        
        # 2. HTTP Status Codes Handling
        if r.status_code == 401:
            return make_provider_error(provider, "Gelbooru rejected the configured API credentials.")
        if r.status_code == 403:
            return make_provider_error(provider, "Gelbooru denied this request. Check account/API access.")
        if r.status_code == 429:
            retry_after = r.headers.get("Retry-After")
            msg = "Too many requests. Please try again later."
            if retry_after:
                msg = f"Too many requests. Retry after {retry_after} seconds."
            return make_provider_error(provider, msg)
        if r.status_code != 200:
            return make_provider_error(provider, f"Gelbooru API returned status code {r.status_code}")
            
        try:
            data = r.json()
        except ValueError:
            return make_provider_error(provider, "Received invalid JSON format from Gelbooru.")
            
        posts = data.get("post", []) if isinstance(data, dict) else []
        
        normalized_results = []
        for post in posts:
            if not isinstance(post, dict):
                continue
                
            # Filter deleted posts or missing IDs
            post_id = post.get("id")
            if not post_id or post.get("status") == "deleted":
                continue
                
            # Safe rating check - keep only general/sensitive/safe ratings if safe_mode is active.
            upstream_rating = post.get("rating")
            if safe_mode and upstream_rating not in ("general", "sensitive", "safe"):
                continue
                
            preview_url = post.get("preview_url") or post.get("sample_url") or post.get("file_url")
            if not preview_url:
                continue
                
            normalized_results.append({
                "source": provider,
                "source_label": "Gelbooru",
                "post_id": str(post_id),
                "post_url": f"https://gelbooru.com/index.php?page=post&s=view&id={post_id}",
                "preview_url": safe_external_image_url(preview_url),
                "sample_url": safe_external_image_url(post.get("sample_url")),
                "file_url": safe_external_image_url(post.get("file_url")),
                "thumbnail_url": safe_external_image_url(preview_url),
                "display_url": safe_external_image_url(post.get("sample_url") or post.get("file_url") or preview_url),
                "original_url": safe_external_image_url(post.get("file_url")),
                "width": int(post.get("width") or 0),
                "height": int(post.get("height") or 0),
                "rating": normalize_rating(upstream_rating),
                "score": int(post.get("score") or 0),
                "created_at": post.get("created_at"),
                "tags": sanitize_tag_list(post.get("tags")),
                "artist_tags": [],
                "character_tags": [],
                "copyright_tags": []
            })
            
        return {
            "error": False,
            "provider": provider,
            "results": normalized_results,
            "has_more": len(posts) >= limit
        }
        
    except requests.exceptions.Timeout:
        return make_provider_error(provider, "Connection timed out.")
    except Exception as e:
        return make_provider_error(provider, "Search failed due to a system error.")

def fetch_danbooru_tag_suggestions(active_token: str) -> list:
    """
    Fetch tag suggestions from Danbooru JSON API.
    """
    try:
        url = "https://danbooru.donmai.us/tags.json"
        params = {
            "search[name_matches]": f"{active_token}*",
            "limit": 10
        }
        headers = {
            "User-Agent": USER_AGENT
        }
        r = requests.get(url, params=params, headers=headers, timeout=5)
        if r.status_code != 200:
            return []
            
        data = r.json()
        if not isinstance(data, list):
            return []
            
        category_map = {
            0: "general",
            1: "artist",
            3: "copyright",
            4: "character",
            5: "meta"
        }
        
        suggestions = []
        for item in data:
            name = item.get("name")
            if not name:
                continue
            cat_id = item.get("category")
            category = category_map.get(cat_id, "unknown")
            post_count = int(item.get("post_count") or 0)
            
            suggestions.append({
                "tag": name,
                "label": name.replace("_", " "),
                "category": category,
                "post_count": post_count,
                "source": "danbooru"
            })
        return suggestions
    except Exception:
        return []

def fetch_gelbooru_tag_suggestions(active_token: str) -> list:
    """
    Fetch tag suggestions from Gelbooru JSON API.
    """
    try:
        # Load dotenv dynamically for server environment credentials
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
            
        user_id = os.environ.get("GELBOORU_USER_ID")
        api_key = os.environ.get("GELBOORU_API_KEY")
        
        url = "https://gelbooru.com/index.php"
        params = {
            "page": "dapi",
            "s": "tag",
            "q": "index",
            "json": 1,
            "name_pattern": f"{active_token}%",
            "orderby": "count",
            "order": "DESC",
            "limit": 10
        }
        
        if user_id and api_key:
            params["api_key"] = api_key
            params["user_id"] = user_id
            
        headers = {
            "User-Agent": USER_AGENT
        }
        r = requests.get(url, params=params, headers=headers, timeout=5)
        if r.status_code != 200:
            return []
            
        try:
            data = r.json()
        except ValueError:
            return []
            
        if not isinstance(data, dict):
            return []
            
        tag_list = data.get("tag", [])
        if isinstance(tag_list, dict):
            tag_list = [tag_list]
        elif not isinstance(tag_list, list):
            return []
            
        category_map = {
            0: "general",
            1: "artist",
            3: "copyright",
            4: "character",
            5: "meta"
        }
        
        suggestions = []
        for item in tag_list:
            name = item.get("name")
            if not name:
                continue
            cat_id = item.get("type")
            try:
                cat_id = int(cat_id)
            except (ValueError, TypeError):
                cat_id = -1
            category = category_map.get(cat_id, "unknown")
            post_count = int(item.get("count") or 0)
            
            suggestions.append({
                "tag": name,
                "label": name.replace("_", " "),
                "category": category,
                "post_count": post_count,
                "source": "gelbooru"
            })
        return suggestions
    except Exception:
        return []

