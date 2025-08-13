@echo off
echo Fetching latest updates from GitHub...
git pull

echo "Activating main virtual environment..."
source venv/bin/activate

echo "Running the Media Manager update..."
python manager.py update

echo "Deactivating virtual environment."
deactivate

echo "Update complete!"