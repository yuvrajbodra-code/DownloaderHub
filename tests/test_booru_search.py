import unittest
from unittest.mock import patch, MagicMock
import requests

from services.booru_search import (
    validate_booru_tags,
    search_danbooru,
    search_gelbooru,
    sanitize_tag_list,
    normalize_rating,
    safe_external_image_url
)

class TestBooruSearch(unittest.TestCase):

    def setUp(self):
        import os
        self.original_env = {
            "GELBOORU_USER_ID": os.environ.get("GELBOORU_USER_ID"),
            "GELBOORU_API_KEY": os.environ.get("GELBOORU_API_KEY")
        }
        os.environ["GELBOORU_USER_ID"] = "dummy_user"
        os.environ["GELBOORU_API_KEY"] = "dummy_key"

    def tearDown(self):
        import os
        for k, v in self.original_env.items():
            if v is None:
                if k in os.environ:
                    del os.environ[k]
            else:
                os.environ[k] = v

    # ==========================================
    # 1. TAG VALIDATION TESTS
    # ==========================================
    def test_valid_tag_input(self):
        # Normal tags, underscores, hyphens, colons, parentheses
        valid_queries = [
            "1girl blue_hair",
            "character_name",
            "artist:name",
            "rating:safe",
            "solo (artwork)",
            "  extra   spaces  "
        ]
        for q in valid_queries:
            with self.subTest(query=q):
                cleaned = validate_booru_tags(q)
                self.assertIsNotNone(cleaned)
                self.assertTrue(len(cleaned) > 0)

    def test_invalid_tag_input(self):
        # Empty inputs, URLs, HTML tags, control characters, special symbols
        invalid_queries = [
            "",
            "   ",
            "a" * 201,  # Too long
            "http://example.com",
            "https://danbooru.donmai.us/posts",
            "<html>test</html>",
            "1girl <script>",
            "1girl\nblue_hair",
            "1girl\rblue_hair",
            "1girl\x00blue_hair",
            "1girl; select * from posts",  # Semicolon disallowed
            "1girl & blue_hair"  # Ampersand disallowed
        ]
        for q in invalid_queries:
            with self.subTest(query=q):
                with self.assertRaises(ValueError):
                    validate_booru_tags(q)

    # ==========================================
    # 2. QUERY CLEANING & RATING INJECTION TESTS
    # ==========================================
    @patch('requests.get')
    def test_safe_tag_injection_danbooru(self, mock_get):
        # Setup mock success response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_get.return_value = mock_resp

        # Search with 1 tag (should append rating:g)
        search_danbooru("1girl")
        called_args, called_kwargs = mock_get.call_args
        self.assertIn("tags", called_kwargs["params"])
        self.assertEqual(called_kwargs["params"]["tags"], "1girl rating:g")

        # Search with 2 tags (should NOT append rating:g to avoid 2-tag anonymous limit)
        search_danbooru("1girl blue_hair")
        called_args, called_kwargs = mock_get.call_args
        self.assertEqual(called_kwargs["params"]["tags"], "1girl blue_hair")

    @patch('requests.get')
    def test_safe_tag_injection_gelbooru(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}
        mock_get.return_value = mock_resp

        # Gelbooru allows multiple tags, we always append rating:general
        search_gelbooru("1girl blue_hair")
        called_args, called_kwargs = mock_get.call_args
        self.assertIn("tags", called_kwargs["params"])
        self.assertEqual(called_kwargs["params"]["tags"], "1girl blue_hair rating:general")

    @patch('requests.get')
    def test_attempt_to_search_unsafe_ratings(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_get.return_value = mock_resp

        # Attempting explicit rating should get stripped/ignored
        search_danbooru("1girl rating:explicit rating:q rating:e rating:questionable")
        called_args, called_kwargs = mock_get.call_args
        # Should clean query, leaving only "1girl" + "rating:g" (since cleaned user tag count is 1)
        self.assertEqual(called_kwargs["params"]["tags"], "1girl rating:g")

        mock_resp.json.return_value = {}
        search_gelbooru("1girl rating:explicit rating:questionable")
        called_args, called_kwargs = mock_get.call_args
        self.assertEqual(called_kwargs["params"]["tags"], "1girl rating:general")


    # ==========================================
    # 3. NORMALIZATION TESTS
    # ==========================================
    @patch('requests.get')
    def test_danbooru_successful_normalization(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Simulated Danbooru payload with g (general) and s (sensitive) posts
        mock_resp.json.return_value = [
            {
                "id": 111,
                "created_at": "2026-06-24T18:00:00Z",
                "image_width": 800,
                "image_height": 600,
                "rating": "g",
                "score": 15,
                "tag_string": "1girl solo blue_hair",
                "tag_string_artist": "artist_a",
                "tag_string_character": "character_b",
                "tag_string_copyright": "franchise_c",
                "preview_file_url": "https://danbooru.donmai.us/preview/111.jpg",
                "large_file_url": "https://danbooru.donmai.us/sample/111.jpg",
                "file_url": "https://danbooru.donmai.us/original/111.jpg",
                "is_deleted": False,
                "is_banned": False
            },
            {
                "id": 222,
                "rating": "e",  # Should be filtered out due to safety constraint
                "tag_string": "unsafe_tag",
                "is_deleted": False,
                "is_banned": False
            }
        ]
        mock_get.return_value = mock_resp

        response = search_danbooru("1girl")
        self.assertFalse(response["error"])
        results = response["results"]
        
        # Excluded explicit rating (id 222), keeping only general (id 111)
        self.assertEqual(len(results), 1)
        
        post = results[0]
        self.assertEqual(post["source"], "danbooru")
        self.assertEqual(post["source_label"], "Danbooru")
        self.assertEqual(post["post_id"], "111")
        self.assertEqual(post["post_url"], "https://danbooru.donmai.us/posts/111")
        self.assertEqual(post["preview_url"], "https://danbooru.donmai.us/preview/111.jpg")
        self.assertEqual(post["thumbnail_url"], "https://danbooru.donmai.us/preview/111.jpg")
        self.assertEqual(post["display_url"], "https://danbooru.donmai.us/sample/111.jpg")
        self.assertEqual(post["original_url"], "https://danbooru.donmai.us/original/111.jpg")
        self.assertEqual(post["rating"], "safe")
        self.assertEqual(post["score"], 15)
        self.assertIn("1girl", post["tags"])
        self.assertEqual(post["artist_tags"], ["artist_a"])
        self.assertEqual(post["character_tags"], ["character_b"])
        self.assertEqual(post["copyright_tags"], ["franchise_c"])

    @patch('requests.get')
    def test_gelbooru_successful_normalization(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Simulated Gelbooru payload
        mock_resp.json.return_value = {
            "post": [
                {
                    "id": 333,
                    "created_at": "Sat May 16 19:28:44 -0500 2009",
                    "width": 1024,
                    "height": 768,
                    "rating": "general",
                    "score": 42,
                    "tags": "1girl green_hair scenery",
                    "preview_url": "https://gelbooru.com/preview/333.jpg",
                    "sample_url": "https://gelbooru.com/sample/333.jpg",
                    "file_url": "https://gelbooru.com/original/333.jpg",
                    "status": "active"
                },
                {
                    "id": 444,
                    "rating": "questionable",  # Filtered out
                    "status": "active"
                }
            ]
        }
        mock_get.return_value = mock_resp

        response = search_gelbooru("1girl")
        self.assertFalse(response["error"])
        results = response["results"]
        
        # Omitted rating:questionable (id 444)
        self.assertEqual(len(results), 1)
        
        post = results[0]
        self.assertEqual(post["source"], "gelbooru")
        self.assertEqual(post["source_label"], "Gelbooru")
        self.assertEqual(post["post_id"], "333")
        self.assertEqual(post["post_url"], "https://gelbooru.com/index.php?page=post&s=view&id=333")
        self.assertEqual(post["preview_url"], "https://gelbooru.com/preview/333.jpg")
        self.assertEqual(post["thumbnail_url"], "https://gelbooru.com/preview/333.jpg")
        self.assertEqual(post["display_url"], "https://gelbooru.com/sample/333.jpg")
        self.assertEqual(post["original_url"], "https://gelbooru.com/original/333.jpg")
        self.assertEqual(post["rating"], "safe")
        self.assertEqual(post["score"], 42)
        self.assertEqual(post["tags"], ["1girl", "green_hair", "scenery"])
        self.assertEqual(post["artist_tags"], [])

    # ==========================================
    # 4. EDGE CASE TESTS
    # ==========================================
    @patch('requests.get')
    def test_missing_preview_image(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # No preview/file urls present in Danbooru response
        mock_resp.json.return_value = [
            {
                "id": 555,
                "rating": "g",
                "tag_string": "scenery"
            }
        ]
        mock_get.return_value = mock_resp

        response = search_danbooru("scenery")
        # Should safely skip the post that does not have a preview URL
        self.assertEqual(len(response["results"]), 0)

    @patch('requests.get')
    def test_upstream_timeout(self, mock_get):
        # Simulate timeout exception raised by requests
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")

        response = search_danbooru("1girl")
        self.assertTrue(response["error"])
        self.assertEqual(response["message"], "Connection timed out.")
        self.assertEqual(response["results"], [])

    @patch('requests.get')
    def test_upstream_429(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {}
        mock_get.return_value = mock_resp

        response = search_gelbooru("1girl")
        self.assertTrue(response["error"])
        self.assertEqual(response["message"], "Too many requests. Please try again later.")

    @patch('requests.get')
    def test_upstream_429_with_retry_after(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "45"}
        mock_get.return_value = mock_resp

        response = search_gelbooru("1girl")
        self.assertTrue(response["error"])
        self.assertEqual(response["message"], "Too many requests. Retry after 45 seconds.")

    @patch('dotenv.load_dotenv')
    def test_gelbooru_missing_credentials(self, mock_load):
        # Temporarily clear environmental variables
        with patch.dict('os.environ', {}, clear=True):
            response = search_gelbooru("1girl")
            self.assertTrue(response["error"])
            self.assertEqual(response["message"], "Gelbooru is not configured. Add GELBOORU_USER_ID and GELBOORU_API_KEY on the server.")

    @patch('requests.get')
    def test_gelbooru_401_credentials_rejected(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp

        response = search_gelbooru("1girl")
        self.assertTrue(response["error"])
        self.assertEqual(response["message"], "Gelbooru rejected the configured API credentials.")

    @patch('requests.get')
    def test_gelbooru_403_access_denied(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_get.return_value = mock_resp

        response = search_gelbooru("1girl")
        self.assertTrue(response["error"])
        self.assertEqual(response["message"], "Gelbooru denied this request. Check account/API access.")

    @patch('requests.get')
    def test_gelbooru_successful_authenticated_request_params(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"post": []}
        mock_get.return_value = mock_resp

        # Call Gelbooru search with custom page and limit
        response = search_gelbooru("1girl blue_hair", page=3, limit=12)
        self.assertFalse(response["error"])
        
        called_args, called_kwargs = mock_get.call_args
        params = called_kwargs["params"]
        
        # Verify custom params are sent to Gelbooru
        self.assertEqual(params["api_key"], "dummy_key")
        self.assertEqual(params["user_id"], "dummy_user")
        self.assertEqual(params["tags"], "1girl blue_hair rating:general")
        self.assertEqual(params["pid"], 2)  # page 3 -> pid 2
        self.assertEqual(params["limit"], 12)

    @patch('requests.get')
    def test_malformed_json(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Simulate invalid json response by throwing a ValueError on json() call
        mock_resp.json.side_effect = ValueError("No JSON object could be decoded")
        mock_get.return_value = mock_resp

        response = search_gelbooru("1girl")
        self.assertTrue(response["error"])
        self.assertEqual(response["message"], "Received invalid JSON format from Gelbooru.")

    @patch('requests.get')
    def test_danbooru_unsafe_mode_normalization(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "id": 111,
                "created_at": "2026-06-24T18:00:00Z",
                "image_width": 800,
                "image_height": 600,
                "rating": "g",
                "preview_file_url": "https://danbooru.donmai.us/preview/111.jpg",
                "large_file_url": "https://danbooru.donmai.us/sample/111.jpg",
                "file_url": "https://danbooru.donmai.us/original/111.jpg",
            },
            {
                "id": 222,
                "rating": "e",
                "preview_file_url": "https://danbooru.donmai.us/preview/222.jpg",
                "large_file_url": "https://danbooru.donmai.us/sample/222.jpg",
                "file_url": "https://danbooru.donmai.us/original/222.jpg",
            }
        ]
        mock_get.return_value = mock_resp

        response = search_danbooru("1girl", safe_mode=False)
        self.assertFalse(response["error"])
        results = response["results"]
        # In unsafe mode, explicit post (id 222) is kept!
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["post_id"], "111")
        self.assertEqual(results[1]["post_id"], "222")
        self.assertEqual(results[1]["rating"], "explicit")

    @patch('requests.get')
    def test_gelbooru_unsafe_mode_normalization(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "post": [
                {
                    "id": 333,
                    "created_at": "Sat May 16 19:28:44 -0500 2009",
                    "width": 1024,
                    "height": 768,
                    "rating": "general",
                    "preview_url": "https://gelbooru.com/preview/333.jpg",
                    "status": "active"
                },
                {
                    "id": 444,
                    "rating": "questionable",
                    "preview_url": "https://gelbooru.com/preview/444.jpg",
                    "status": "active"
                }
            ]
        }
        mock_get.return_value = mock_resp

        response = search_gelbooru("1girl", safe_mode=False)
        self.assertFalse(response["error"])
        results = response["results"]
        # In unsafe mode, questionable post (id 444) is kept!
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["post_id"], "333")
        self.assertEqual(results[1]["post_id"], "444")
        self.assertEqual(results[1]["rating"], "questionable")

class TestDiscoverApi(unittest.TestCase):
    def setUp(self):
        from app import app, DISCOVER_CACHE, RATE_LIMIT_STORE
        app.config['TESTING'] = True
        self.client = app.test_client()
        # Reset caching and rate limiting state before each test
        DISCOVER_CACHE.clear()
        RATE_LIMIT_STORE.clear()

    # - both sources success
    @patch('app.booru_search_danbooru')
    @patch('app.booru_search_gelbooru')
    def test_both_sources_success(self, mock_gel, mock_dan):
        mock_dan.return_value = {
            "error": False,
            "provider": "danbooru",
            "results": [
                {
                    "source": "danbooru",
                    "post_id": "1",
                    "created_at": "2026-06-24T18:00:00Z"
                }
            ],
            "has_more": True
        }
        mock_gel.return_value = {
            "error": False,
            "provider": "gelbooru",
            "results": [
                {
                    "source": "gelbooru",
                    "post_id": "2",
                    "created_at": "2026-06-24T18:05:00Z"
                }
            ],
            "has_more": False
        }

        resp = self.client.get('/api/discover/booru-search?q=1girl')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["query"], "1girl")
        self.assertEqual(len(data["results"]), 2)
        # Check sort: newest first (Gelbooru post_id 2 has 18:05:00, Danbooru post_id 1 has 18:00:00)
        self.assertEqual(data["results"][0]["post_id"], "2")
        self.assertEqual(data["results"][1]["post_id"], "1")
        self.assertEqual(data["has_more"]["danbooru"], True)
        self.assertEqual(data["has_more"]["gelbooru"], False)

    # - one source fails
    @patch('app.booru_search_danbooru')
    @patch('app.booru_search_gelbooru')
    def test_one_source_fails(self, mock_gel, mock_dan):
        mock_dan.return_value = {
            "error": True,
            "provider": "danbooru",
            "message": "Connection timed out.",
            "results": [],
            "has_more": False
        }
        mock_gel.return_value = {
            "error": False,
            "provider": "gelbooru",
            "results": [
                {
                    "source": "gelbooru",
                    "post_id": "2",
                    "created_at": "2026-06-24T18:05:00Z"
                }
            ],
            "has_more": False
        }

        resp = self.client.get('/api/discover/booru-search?q=1girl')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(len(data["errors"]), 1)
        self.assertEqual(data["errors"][0]["source"], "danbooru")
        self.assertEqual(data["errors"][0]["message"], "Connection timed out.")

    # - invalid source
    def test_invalid_source(self):
        resp = self.client.get('/api/discover/booru-search?q=1girl&sources=danbooru,invalid_site')
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertTrue(data["error"])
        self.assertIn("Invalid source", data["message"])

    # - missing q
    def test_missing_q(self):
        resp = self.client.get('/api/discover/booru-search')
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertTrue(data["error"])
        self.assertIn("required", data["message"])

    # - invalid page
    def test_invalid_page(self):
        resp = self.client.get('/api/discover/booru-search?q=1girl&page=abc')
        self.assertEqual(resp.status_code, 400)
        resp2 = self.client.get('/api/discover/booru-search?q=1girl&page=0')
        self.assertEqual(resp2.status_code, 400)

    # - cache hit
    @patch('app.booru_search_danbooru')
    @patch('app.booru_search_gelbooru')
    def test_cache_hit(self, mock_gel, mock_dan):
        mock_dan.return_value = {
            "error": False, "provider": "danbooru", "results": [], "has_more": False
        }
        mock_gel.return_value = {
            "error": False, "provider": "gelbooru", "results": [], "has_more": False
        }

        # First request (sets cache)
        resp1 = self.client.get('/api/discover/booru-search?q=1girl')
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(mock_dan.call_count, 1)

        # Second request (cache hit)
        resp2 = self.client.get('/api/discover/booru-search?q=1girl')
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(mock_dan.call_count, 1) # Count remains 1!

    # - rate-limit response
    @patch('app.booru_search_danbooru')
    @patch('app.booru_search_gelbooru')
    def test_rate_limit_response(self, mock_gel, mock_dan):
        mock_dan.return_value = {
            "error": False, "provider": "danbooru", "results": [], "has_more": False
        }
        mock_gel.return_value = {
            "error": False, "provider": "gelbooru", "results": [], "has_more": False
        }

        # Send 15 requests (which is allowed)
        for i in range(15):
            resp = self.client.get(f'/api/discover/booru-search?q=1girl&page={i+1}')
            self.assertEqual(resp.status_code, 200)

        # 16th request triggers rate limit
        resp_blocked = self.client.get('/api/discover/booru-search?q=1girl&page=16')
        self.assertEqual(resp_blocked.status_code, 429)
        data = resp_blocked.get_json()
        self.assertTrue(data["error"])
        self.assertIn("Too many requests", data["message"])

    # - safe-mode enforcement
    @patch('app.booru_search_danbooru')
    @patch('app.booru_search_gelbooru')
    def test_safe_mode_enforcement(self, mock_gel, mock_dan):
        mock_dan.return_value = {"error": False, "provider": "danbooru", "results": [], "has_more": False}
        mock_gel.return_value = {"error": False, "provider": "gelbooru", "results": [], "has_more": False}
        
        # Test safe mode active (by default or safe_mode=true)
        resp = self.client.get('/api/discover/booru-search?q=1girl+rating:explicit')
        self.assertEqual(resp.status_code, 200)
        # Stripped of rating:explicit! Default safe_mode=True passed
        mock_dan.assert_called_once_with("1girl", 1, 20, True) 

        mock_dan.reset_mock()
        mock_gel.reset_mock()

        # Test safe mode disabled (safe_mode=false)
        resp2 = self.client.get('/api/discover/booru-search?q=1girl+rating:explicit&safe_mode=false')
        self.assertEqual(resp2.status_code, 200)
        # rating:explicit is NOT stripped! safe_mode=False passed
        mock_dan.assert_called_once_with("1girl rating:explicit", 1, 20, False)

    # - cache hit separates safe modes
    @patch('app.booru_search_danbooru')
    @patch('app.booru_search_gelbooru')
    def test_cache_hit_separates_safe_modes(self, mock_gel, mock_dan):
        mock_dan.return_value = {
            "error": False, "provider": "danbooru", "results": [], "has_more": False
        }
        mock_gel.return_value = {
            "error": False, "provider": "gelbooru", "results": [], "has_more": False
        }

        # Request in safe mode
        resp1 = self.client.get('/api/discover/booru-search?q=1girl&safe_mode=true')
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(mock_dan.call_count, 1)

        # Request again in safe mode (cache hit)
        resp2 = self.client.get('/api/discover/booru-search?q=1girl&safe_mode=true')
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(mock_dan.call_count, 1) # count is still 1

        # Request in unsafe mode (should not hit safe cache!)
        resp3 = self.client.get('/api/discover/booru-search?q=1girl&safe_mode=false')
        self.assertEqual(resp3.status_code, 200)
        self.assertEqual(mock_dan.call_count, 2) # count increments to 2!

class TestTagSuggestions(unittest.TestCase):
    def setUp(self):
        from app import app, TAG_SUGGESTIONS_CACHE, TAG_LIMIT_STORE
        app.config['TESTING'] = True
        self.client = app.test_client()
        TAG_SUGGESTIONS_CACHE.clear()
        TAG_LIMIT_STORE.clear()

    # Test extracting final token and prefix from q
    @patch('app.fetch_danbooru_tag_suggestions')
    @patch('app.fetch_gelbooru_tag_suggestions')
    def test_token_extraction(self, mock_gel, mock_dan):
        mock_dan.return_value = []
        mock_gel.return_value = []
        
        # 1. Multi-tag input
        resp = self.client.get('/api/discover/tag-suggestions?q=1girl+blue+ha')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["active_token"], "ha")
        self.assertEqual(data["prefix"], "1girl blue ")
        mock_dan.assert_called_with("ha")
        mock_gel.assert_called_with("ha")

        # 2. Single-tag input
        resp2 = self.client.get('/api/discover/tag-suggestions?q=1girl')
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.get_json()
        self.assertEqual(data2["active_token"], "1girl")
        self.assertEqual(data2["prefix"], "")
        mock_dan.assert_called_with("1girl")
        mock_gel.assert_called_with("1girl")

    # Test ignore cases
    @patch('app.fetch_danbooru_tag_suggestions')
    @patch('app.fetch_gelbooru_tag_suggestions')
    def test_ignore_rules(self, mock_gel, mock_dan):
        # 1. Empty input
        resp_empty = self.client.get('/api/discover/tag-suggestions?q=')
        self.assertEqual(resp_empty.status_code, 200)
        self.assertEqual(resp_empty.get_json()["suggestions"], [])
        self.assertEqual(mock_dan.call_count, 0)

        # 2. 1-character token
        resp_short = self.client.get('/api/discover/tag-suggestions?q=a')
        self.assertEqual(resp_short.status_code, 200)
        self.assertEqual(resp_short.get_json()["suggestions"], [])
        self.assertEqual(mock_dan.call_count, 0)

        # 3. Negative tag
        resp_neg = self.client.get('/api/discover/tag-suggestions?q=-blue_hair')
        self.assertEqual(resp_neg.status_code, 200)
        self.assertEqual(resp_neg.get_json()["suggestions"], [])
        self.assertEqual(mock_dan.call_count, 0)

        # 4. Metatag
        resp_meta = self.client.get('/api/discover/tag-suggestions?q=rating:safe')
        self.assertEqual(resp_meta.status_code, 200)
        self.assertEqual(resp_meta.get_json()["suggestions"], [])
        self.assertEqual(mock_dan.call_count, 0)

        resp_meta2 = self.client.get('/api/discover/tag-suggestions?q=1girl+rating:')
        self.assertEqual(resp_meta2.status_code, 200)
        self.assertEqual(resp_meta2.get_json()["suggestions"], [])
        self.assertEqual(mock_dan.call_count, 0)

    # Test Danbooru normalization
    @patch('requests.get')
    def test_danbooru_normalization(self, mock_get):
        from services.booru_search import fetch_danbooru_tag_suggestions
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"name": "blue_hair", "category": 0, "post_count": 1200000},
            {"name": "artist_a", "category": 1, "post_count": 50},
            {"name": "copyright_b", "category": 3, "post_count": 10},
            {"name": "character_c", "category": 4, "post_count": 20},
            {"name": "meta_d", "category": 5, "post_count": 5},
            {"name": "unknown_e", "category": 99, "post_count": 1}
        ]
        mock_get.return_value = mock_resp

        results = fetch_danbooru_tag_suggestions("blue_ha")
        self.assertEqual(len(results), 6)
        
        self.assertEqual(results[0]["tag"], "blue_hair")
        self.assertEqual(results[0]["label"], "blue hair")
        self.assertEqual(results[0]["category"], "general")
        self.assertEqual(results[0]["post_count"], 1200000)
        self.assertEqual(results[0]["source"], "danbooru")

        self.assertEqual(results[1]["category"], "artist")
        self.assertEqual(results[2]["category"], "copyright")
        self.assertEqual(results[3]["category"], "character")
        self.assertEqual(results[4]["category"], "meta")
        self.assertEqual(results[5]["category"], "unknown")

    # Test source merging and sorting
    @patch('app.fetch_danbooru_tag_suggestions')
    @patch('app.fetch_gelbooru_tag_suggestions')
    def test_merging_and_sorting(self, mock_gel, mock_dan):
        mock_dan.return_value = [
            {"tag": "blue_hair", "label": "blue hair", "category": "general", "post_count": 100, "source": "danbooru"},
            {"tag": "hair_blue", "label": "hair blue", "category": "general", "post_count": 500, "source": "danbooru"}
        ]
        mock_gel.return_value = [
            {"tag": "blue_hair", "label": "blue hair", "category": "general", "post_count": 200, "source": "gelbooru"},
            {"tag": "blue_hat", "label": "blue hat", "category": "general", "post_count": 50, "source": "gelbooru"}
        ]

        resp = self.client.get('/api/discover/tag-suggestions?q=blue_ha')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        suggestions = data["suggestions"]
        
        self.assertEqual(len(suggestions), 3)
        self.assertEqual(suggestions[0]["tag"], "blue_hair")
        self.assertEqual(sorted(suggestions[0]["sources"]), ["danbooru", "gelbooru"])
        self.assertEqual(suggestions[0]["post_count"], 200)

        self.assertEqual(suggestions[1]["tag"], "blue_hat")
        self.assertEqual(suggestions[1]["sources"], ["gelbooru"])
        self.assertEqual(suggestions[1]["post_count"], 50)

        self.assertEqual(suggestions[2]["tag"], "hair_blue")
        self.assertEqual(suggestions[2]["sources"], ["danbooru"])
        self.assertEqual(suggestions[2]["post_count"], 500)

    # Test cache behavior
    @patch('app.fetch_danbooru_tag_suggestions')
    @patch('app.fetch_gelbooru_tag_suggestions')
    def test_cache_behavior(self, mock_gel, mock_dan):
        mock_dan.return_value = []
        mock_gel.return_value = []

        # 1st request -> cache miss
        self.client.get('/api/discover/tag-suggestions?q=blue_ha')
        self.assertEqual(mock_dan.call_count, 1)

        # 2nd request -> cache hit
        self.client.get('/api/discover/tag-suggestions?q=blue_ha')
        self.assertEqual(mock_dan.call_count, 1)

    # Test one provider failure
    @patch('app.fetch_danbooru_tag_suggestions')
    @patch('app.fetch_gelbooru_tag_suggestions')
    def test_one_provider_failure(self, mock_gel, mock_dan):
        mock_dan.return_value = [
            {"tag": "blue_hair", "label": "blue hair", "category": "general", "post_count": 100, "source": "danbooru"}
        ]
        mock_gel.side_effect = Exception("Gelbooru Offline")

        resp = self.client.get('/api/discover/tag-suggestions?q=blue_ha')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        
        suggestions = data["suggestions"]
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["tag"], "blue_hair")
        self.assertEqual(suggestions[0]["sources"], ["danbooru"])

if __name__ == '__main__':
    unittest.main()
