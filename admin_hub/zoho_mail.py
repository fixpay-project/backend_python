import requests
import time

# Configuration
CLIENT_ID = '1000.9E8ZEJ0URFAK5CV5IOB7VN5C8Q62VU'
CLIENT_SECRET = '72951572d69ce6a850dd03608ddd900f2bce40790d'
REFRESH_TOKEN = '1000.150114da22d9977ccc9c62e853dfb247.9f1fdf7e01d4db2d10da8ebff437f1ef'
FROM_EMAIL = 'noreply@fixpay.in'


_access_token = None
_token_expiry = 0
_account_id = None

MAIL_API_BASE = "https://mail.zoho.in/api"

import time
import requests


def log_to_file(text, filename="zoho_log.txt"):
    with open(filename, "a", encoding="utf-8") as f:
        f.write(text + "\n")

def fetch_access_token():
    global _access_token, _token_expiry

    log_to_file("Refreshing access token...")
    url = "https://accounts.zoho.in/oauth/v2/token"
    data = {
        'refresh_token': REFRESH_TOKEN,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'refresh_token'
    }

    resp = requests.post(url, data=data)
    log_to_file(f"Token Response: {resp.status_code} - {resp.text}")
    result = resp.json()

    if 'access_token' in result:
        _access_token = result['access_token']
        _token_expiry = time.time() + int(result.get('expires_in', 3600)) - 60
        log_to_file("Access token fetched successfully.")
        return _access_token
    else:
        err_msg = f"Failed to refresh access token: {result}"
        log_to_file(err_msg)
        raise Exception(err_msg)


def get_access_token():
    global _access_token, _token_expiry

    if _access_token and time.time() < _token_expiry:
        log_to_file("Using cached access token.")
        return _access_token
    else:
        return fetch_access_token()


def get_account_id():
    global _account_id
    if _account_id:
        log_to_file("Using cached account ID.")
        return _account_id

    token = get_access_token()
    url = f"{MAIL_API_BASE}/accounts"
    headers = {
        "Authorization": f"Zoho-oauthtoken {token}"
    }

    log_to_file("Fetching account ID...")
    resp = requests.get(url, headers=headers)
    log_to_file(f"Account Response: {resp.status_code} - {resp.text}")

    if resp.status_code == 200:
        data = resp.json()
        _account_id = data['data'][0]['accountId']
        log_to_file(f"Account ID fetched: {_account_id}")
        return _account_id
    else:
        err_msg = f"Failed to get account ID: {resp.json()}"
        log_to_file(err_msg)
        raise Exception(err_msg)


def check_auth_token(token):
    url = f"{MAIL_API_BASE}/accounts"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Zoho-oauthtoken {token}"
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        log_to_file("Auth token is valid. Data received:")
        log_to_file(str(response.json()))
    else:
        log_to_file(f"Auth token invalid or error occurred: {response.status_code}")
        log_to_file(response.text)


def zoho_send_email(to_email, subject, content_text):
    token = get_access_token()
    check_auth_token(token)
    account_id = get_account_id()

    to_email = to_email.strip()

    log_to_file(f"Sending email to: {to_email!r}")

    url = f"https://mail.zoho.in/api/accounts/{account_id}/messages"
    headers = {
        "Authorization": f"Zoho-oauthtoken {token}",
        "Content-Type": "application/json"
    }

    data = {
        "fromAddress": FROM_EMAIL,
        "toAddress": to_email,
        "ccAddress": "",         # Optional
        "bccAddress": "",        # Optional
        "subject": subject,
        "content": content_text,
        "mailFormat": "html",    # or "plaintext"
        "askReceipt": "no",      # or "yes"
        "encoding": "UTF-8",
        "isSchedule": False
    }

    log_to_file(f"POST URL: {url}")
    log_to_file(f"Headers: {headers}")
    log_to_file(f"Payload: {data}")

    resp = requests.post(url, headers=headers, json=data)
    log_to_file(f"Email Send Response: {resp.status_code} - {resp.text}")

    if resp.status_code == 200:
        log_to_file("✅ Email sent successfully.")
        return True
    else:
        log_to_file("❌ Failed to send email.")
        return False

