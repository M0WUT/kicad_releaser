import json
import logging
from typing import Optional
import re

import requests


class FarnellBaseRequest:
    BASE_URL = "https://api.element14.com/catalog/products?"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def get(self, options: dict[str:str]) -> requests.Response:
        url = self.BASE_URL
        for option, value in options.items():
            url += f"{option}={value}&"
        url += f"callinfo.apikey={self.api_key}"

        return requests.get(url)


class FarnellAPI:
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

    def check_for_stock(self, part_number: str) -> int:
        try:
            self.logger.debug(f"Checking stock for {part_number}")
            part_number = re.sub("#", "%23", part_number)
            x = FarnellBaseRequest(self.api_key)
            https_options = {
                "versionNumber": 1.3,
                "term": f"manuPartNum:{part_number}",
                "storeInfo.id": "uk.farnell.com",
                "resultsSettings.offset": 0,
                "resultsSettings.numberOfResults": 10,
                "resultsSettings.responseGroup": "inventory",
                "callInfo.omitXmlSchema": False,
                "callInfo.responseDataFormat": "json",
            }

            response = x.get(options=https_options)
            result = response.json()["manufacturerPartNumberSearchReturn"]

            num_results = int(result["numberOfResults"])

            if num_results == 0:
                return -1  # MPN not found

            for product in result["products"]:
                if int(product["translatedMinimumOrderQuality"]) <= 10:
                    try:
                        for x in product["stock"]["breakdown"]:
                            if x["region"] == "UK" and int(x["inv"]):
                                return int(x["inv"])
                    except KeyError:
                        continue

            return 0  # Didn't find suitable stock
        except:
            raise Exception(part_number)


if __name__ == "__main__":
    logger = logging.getLogger("Mousearch Debug")
    logger.setLevel(logging.DEBUG)
    logger_handler = logging.StreamHandler()
    logger_handler.setLevel(logging.DEBUG)
    logger.addHandler(logger_handler)
    with open("./farnell_key.txt", "r") as file:
        api_key = file.readline()
    x = FarnellAPI(api_key, logger)
    print(x.check_for_stock("RK73H1ETTP1603"))
