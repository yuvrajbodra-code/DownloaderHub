import sys
from app import app, init_db

def main():
    try:
        # Initialize Flask application context safely
        with app.app_context():
            # Confirm database schema exists
            init_db()
            print("X sync command ready")
            sys.exit(0)
    except Exception as e:
        print(f"Error initializing database: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
