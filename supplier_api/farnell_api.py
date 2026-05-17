# Standard imports
import re
import requests

# Third party imports

# Local imports
from supplier_api.supplier_api import SupplierAPI


class FarnellBaseRequest:
    BASE_URL = "https://api.element14.com/catalog/products?"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def get(self, options: dict[str, str]) -> requests.Response:
        url = self.BASE_URL
        for option, value in options.items():
            url += f"{option}={value}&"
        url += f"callinfo.apikey={self.api_key}"

        return requests.get(url)


class FarnellAPI(SupplierAPI):

    def query_stock_quantity(self, part_number: str) -> int:
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
