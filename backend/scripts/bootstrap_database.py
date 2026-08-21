from app.db.bootstrap import bootstrap_database


def main() -> None:
    bootstrap_database()
    print("CityBuddy database extensions and Alembic schema are up to date.")


if __name__ == "__main__":
    main()
