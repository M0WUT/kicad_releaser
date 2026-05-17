# Standard imports
import logging
from typing import Optional

# Third party imports

# Local imports


class SupplierAPI:
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

    def query_stock_quantity(self, part_number: str) -> int:
        """
        Queries for available stock
        Returns stock value or -1 if search fails or isn't unique
        """

        raise NotImplementedError
