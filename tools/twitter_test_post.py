#!/usr/bin/env python3
"""
Twitter Test Post (twitter_test_post.py)
-----------------------------------------
Standalone smoke test for X/Twitter API authentication.

Posts a single test tweet to verify:
- Credentials in credentials.json are valid
- App permissions are set to Read+Write
- tweepy can reach the X API

Usage:
    python tools/twitter_test_post.py

Exits 0 on success (and prints the tweet URL), non-zero on any failure.
"""

import sys
import json
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

try:
    import tweepy
except ImportError:
    print("ERROR: tweepy is not installed. Run: pip install tweepy")
    sys.exit(1)


def main():
    project_root = Path(__file__).parent.parent
    creds_path = project_root / "credentials.json"

    if not creds_path.exists():
        print(f"ERROR: {creds_path} not found")
        sys.exit(1)

    with open(creds_path, "r", encoding="utf-8") as f:
        creds = json.load(f)

    twitter = creds.get("twitter_api")
    if not twitter:
        print("ERROR: 'twitter_api' block missing from credentials.json")
        sys.exit(1)

    required = ["api_key", "api_key_secret", "access_token", "access_token_secret"]
    for k in required:
        v = twitter.get(k, "")
        if not v or v.startswith("PASTE_"):
            print(f"ERROR: '{k}' in credentials.json is empty or still a placeholder")
            sys.exit(1)

    client = tweepy.Client(
        consumer_key=twitter["api_key"],
        consumer_secret=twitter["api_key_secret"],
        access_token=twitter["access_token"],
        access_token_secret=twitter["access_token_secret"],
    )

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = f"Auth smoke test from options scanner — {timestamp}. Disregard."

    print(f"Posting: {text}")

    try:
        resp = client.create_tweet(text=text)
    except tweepy.Unauthorized as e:
        print(f"ERROR: 401 Unauthorized — credentials are wrong or expired.\n{e}")
        sys.exit(1)
    except tweepy.Forbidden as e:
        print(
            "ERROR: 403 Forbidden — most common cause is missing Read+Write "
            "permission. Fix in X Developer Portal under User authentication "
            "settings, then REGENERATE Access Token + Secret (the existing "
            "ones stay read-only even after the permission change).\n"
            f"{e}"
        )
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: unexpected failure: {type(e).__name__}: {e}")
        sys.exit(1)

    tweet_id = resp.data["id"]
    print("SUCCESS — tweet posted")
    print(f"Tweet ID: {tweet_id}")
    print(f"URL: https://x.com/i/status/{tweet_id}")


if __name__ == "__main__":
    main()
