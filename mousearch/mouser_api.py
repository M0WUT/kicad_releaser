import json
import logging
from typing import Optional

import requests


class MouserBaseRequest:
    VERSION = "2"
    BASE_URL = f"https://api.mouser.com/api/v{VERSION}"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def post(self, url, data) -> requests.Response:
        post_headers = {
            "Content-Type": "application/json",
        }
        return requests.post(
            url=f"{self.BASE_URL}/{url}?apiKey={self.api_key}",
            data=json.dumps(data),
            headers=post_headers,
        )


class MouserAPI:
    def __init__(self, api_key: str, logger: Optional[logging.Logger] = None):

        self.api_key = api_key
        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger(__name__)
            self.logger.setLevel(logging.WARNING)
            logger_handler = logging.StreamHandler()
            logger_handler.setLevel(logging.WARNING)
            self.logger.addHandler(logger_handler)

    def search_by_keyword(self, keyword) -> dict:

        self.logger.debug(f"Searching for {keyword}")
        x = MouserBaseRequest(self.api_key)
        result = x.post(
            url="search/keyword",
            data={
                "SearchByKeywordRequest": {
                    "keyword": f"{keyword}",
                }
            },
        ).json()

        errors = result["Errors"]

        assert not errors, f"Query for {keyword} return errors: {errors}"
        return result["SearchResults"]

    def check_for_stock(self, part_number: str) -> int:
        self.logger.debug(f"Checking stock for {part_number}")
        x = MouserBaseRequest(self.api_key)
        result = x.post(
            url="search/keyword",
            data={"SearchByKeywordRequest": {"keyword": f"{part_number}"}},
        ).json()

        errors = result["Errors"]

        assert not errors, f"Query for {part_number} return errors: {errors}"
        # Remove any options for volume ordering and extra long part numbers
        parts = [x for x in result["SearchResults"]["Parts"]]
        if len(parts) == 0:
            return -1
        for x in [y for y in parts if y["Min"] == "1"]:
            in_stock_quantity = int(x["AvailabilityInStock"])
            if in_stock_quantity:
                return in_stock_quantity
        return 0


if __name__ == "__main__":
    logger = logging.getLogger("Mousearch Debug")
    logger.setLevel(logging.DEBUG)
    logger_handler = logging.StreamHandler()
    logger_handler.setLevel(logging.DEBUG)
    logger.addHandler(logger_handler)
    with open("./api_key.txt", "r") as file:
        api_key = file.readline()
    x = MouserAPI(api_key, logger)
    print(x.check_for_stock("RK73H1ETTP2202F"))
