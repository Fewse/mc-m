#!/bin/bash
set -e

# Farben
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}>>> Minecraft Server Manager Installer${NC}"

# 1. Update & Dependencies
echo -e "${GREEN}>>> Updating system and checking dependencies...${NC}"
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv

# Check for Java
if type -p java > /dev/null; then
    echo -e "${GREEN}>>> Java found, skipping installation.${NC}"
    java -version
else
    echo -e "${GREEN}>>> Java not found, installing OpenJDK 17...${NC}"
    sudo apt-get install -y openjdk-17-jre-headless
fi

# 2. Setup Venv
echo -e "${GREEN}>>> Setting up Python virtual environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate

# 3. Install Python libs
echo -e "${GREEN}>>> Installing Python libraries...${NC}"
pip install fastapi uvicorn psutil python-multipart python-jose[cryptography] jinja2 requests websockets

# 4. Create dummy config if not exists
if [ ! -f "config.json" ]; then
    echo -e "${GREEN}>>> Creating default config...${NC}"
    # Config will be auto-created by app on first run, but we can touch it here if needed.
    # Actually, we let the app handle it.
fi

# 5. Service File Generation
echo -e "${GREEN}>>> Generating Systemd Service file (example)...${NC}"
CURRENT_DIR=$(pwd)
USER=$(whoami)

cat > mc-manager.service << EOF
[Unit]
Description=Minecraft Server Manager Web Interface
After=network.target

[Service]
User=$USER
WorkingDirectory=$CURRENT_DIR
ExecStart=$CURRENT_DIR/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

echo -e "${GREEN}>>> Installation Complete!${NC}"
echo -e "You can start the server manually with: ${GREEN}./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000${NC}"
echo -e "To install as a service:"
echo -e "  sudo mv mc-manager.service /etc/systemd/system/"
echo -e "  sudo systemctl daemon-reload"
echo -e "  sudo systemctl enable mc-manager"
echo -e "  sudo systemctl start mc-manager"
echo -e "Access the web interface at http://<your-ip>:8000"
