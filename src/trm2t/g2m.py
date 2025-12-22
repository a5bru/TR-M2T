"""Ginan states to mqtt."""
import time
import traceback
import pymongo
import logging

logger = logging.getLogger(__name__)


# Function to handle changes
def handle_change(change):
    logger.info("Change detected: %s", change)


def run():
    client = pymongo.MongoClient()
    db = client["rt_ppp_example"]
    collection = db["States"]
    try:
        pipeline = [
            {"$match": {"operationType": "insert"}},
            {"$match": {"fullDocument.State": "REC_POS"}}
        ]
        with collection.watch(pipeline) as stream:
            for change in stream:
                handle_change(change)

    except Exception as e:
        logger.error("Error occurred: %s", e)


if __name__ == "__main__":
    run()
