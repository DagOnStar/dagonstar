## SSH public-key authentication for the Raspberry Pi
To send tasks remotely to the Raspberry Pi, you must enable public-key authentication.

You will generate and use SSH keys for this.

On your computer (client), open a terminal and run:
```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
```
(You can use rsa if you prefer, but ed25519 is more secure and faster.)

This will create two files in ~/.ssh/:

id_ed25519 → your private key (do not share this).
id_ed25519.pub → your public key.

Copy the public key to the Raspberry Pi, using the command:
```bash
ssh-copy-id pi@IP_OF_YOUR_RASPBERRY
```
(replace pi with your username and IP_OF_YOUR_RASPBERRY with the real address).

If you don't have ssh-copy-id, you can do it manually:
```bash
cat ~/.ssh/id_ed25519.pub | ssh pi@IP_OF_YOUR_RASPBERRY "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```
Test passwordless login, simply running:
```bash
ssh pi@IP_OF_YOUR_RASPBERRY
```
You should be logged in directly without being prompted for a password.