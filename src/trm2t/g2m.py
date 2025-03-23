"""Ginan states to mqtt."""
import time
import traceback
import pymongo


# Function to handle changes
def handle_change(change):
    print("Change detected:", change)


def run():
    client = pymongo.MongoClient()
    db = client["rt_ppp_example"]
    collection = db["States"]
    try:
        with collection.watch() as stream:
            for change in stream:
                handle_change(change)

    except Exception as e:
        print(f"Error occured: {e}")


if __name__ == "__main__":
    run()
