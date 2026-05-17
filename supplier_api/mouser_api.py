# Standard imports
import json
import logging
import requests

# Third party imports

# Local imports
from supplier_api.supplier_api import SupplierAPI


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


class MouserAPI(SupplierAPI):

    def query_stock_quantity(self, part_number: str) -> int:
        self.logger.debug(f"Checking stock for {part_number}")
        x = MouserBaseRequest(self.api_key)
        result = x.post(
            url="search/keyword",
            data={"SearchByKeywordRequest": {"keyword": f"{part_number}"}},
        ).json()

        errors = result["Errors"]

        assert not errors, f"Query for {part_number} return errors: {errors}"

        parts = [x for x in result["SearchResults"]["Parts"]]
        if len(parts) == 0:
            # Not found
            return -1
        # Only look at options for ordering in one-off
        for x in [y for y in parts if y["Min"] == "1"]:
            in_stock_quantity = x["AvailabilityInStock"]
            if in_stock_quantity:
                return int(in_stock_quantity)
        return 0
