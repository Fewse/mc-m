# HTTPS Einrichtung (SSL) für MC Manager

Um die Verbindung sicher zu machen (besonders wichtig für Passwörter!), nutzen wir **Nginx** als "Reverse Proxy" und **Certbot** für kostenlose Let's Encrypt Zertifikate.

## Voraussetzung
- Du brauchst eine **Domain** (z.B. `mein-server.de` oder `mc.mein-server.de`), die auf die IP deines Servers zeigt (`A-Record`).
- Ports **80** (HTTP) und **443** (HTTPS) müssen in der Firewall/Router offen sein.

## Schritt 1: Installation

```bash
sudo apt update
sudo apt install -y nginx python3-certbot-nginx
```

## Schritt 2: Nginx Konfiguration

Erstelle eine neue Konfigurationsdatei:

```bash
sudo nano /etc/nginx/sites-available/mc-manager
```

Füge folgenden Inhalt ein (tausche `deine-domain.de` aus!):

```nginx
server {
    server_name deine-domain.de;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Aktivieren der Seite:

```bash
sudo ln -s /etc/nginx/sites-available/mc-manager /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default  # (Optional: falls default stört)
sudo nginx -t                             # Testen auf Syntaxfehler
sudo systemctl restart nginx
```

## Schritt 3: SSL Zertifikat holen

Führe Certbot aus. Es wird dich nach einer E-Mail fragen und dann automatisch die Nginx-Config anpassen.

```bash
sudo certbot --nginx -d deine-domain.de
```

Wähle "2" (Redirect), wenn gefragt wird, ob HTTP zu HTTPS umgeleitet werden soll.

**Fertig!** Deine App ist nun unter `https://deine-domain.de` erreichbar.
