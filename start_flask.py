import os, sys

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

# Set port
os.environ.setdefault('PORT', '5002')

# Import and run the Flask app
from app import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    app.run(debug=False, host='0.0.0.0', port=port, use_reloader=False)
