import requests
import os
import json

class DeviceAuthenticator:
    def __init__(self, auth_url="http://localhost:8095", token_file="~/.mycli/token.json"):
        self.auth_url = f"http://{auth_url}" if not auth_url.startswith("http") else auth_url 
        self.token_file = os.path.expanduser(token_file)

    def request_user_code(self):
        resp = requests.post(f"{self.auth_url}/device/code")
        resp.raise_for_status()
        data = resp.json()
        print(f"\nPlease go to {data['verification_uri']}")
        print(f"And enter this code to verify the client: {data['user_code']}\n")
        return data['user_code']

    def input_user_token(self):
        return input("Paste the token shown in your browser here: ").strip()

    def validate_token(self, user_token):
        resp = requests.post(f"{self.auth_url}/token/validate", json={"token": user_token})
        if resp.status_code == 200:
            token_data = resp.json()
            print("✅ Access token received!")
            return token_data
        else:
            print("❌ Invalid token:", resp.json())
            return None

    def save_token(self, token_data):
        os.makedirs(os.path.dirname(self.token_file), exist_ok=True)
        with open(self.token_file, "w") as f:
            json.dump(token_data, f)
        print(f"🔐 Token saved at {self.token_file}")

    def authenticate(self):
        if os.path.exists(self.token_file):
            print(f"Token already exists at {self.token_file}. Skipping authentication.")

            # Load the existing token
            with open(self.token_file, "r") as f:
                token_data = json.load(f)
                self.token_data = token_data

            return

        print("Starting authentication process...")
        self.request_user_code()
        print("Waiting for you to complete the verification in the browser...")

        user_token = self.input_user_token()
        token_data = self.validate_token(user_token)
        if token_data:
            self.save_token(token_data)
            self.token_data = token_data
