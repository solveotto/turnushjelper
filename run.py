from app import create_app

app = create_app()
print('Run: Create App')
 
if __name__ == '__main__':
    import os
    debug = os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1", "yes")
    app.run(port=8080, debug=debug)