import sys
from sqlalchemy import create_engine, text
from app.core.config import settings

def main():
    try:
        engine = create_engine(settings.DATABASE_URL, connect_args={"connect_timeout": 10})
        with engine.connect() as connection:
            res = connection.execute(text("SELECT 1")).scalar_one()
        engine.dispose()
        if res == 1:
            print("DATABASE_OK")
            return 0
        else:
            print("DATABASE_ERROR: Unexpected query result")
            return 1
    except Exception as e:
        print(f"DATABASE_ERROR: {type(e).__name__} - connection failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
