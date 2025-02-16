from math import ceil
from pathlib import Path

import peewee
from fastapi import Query, Request, Response


def _make_index_positive(total: int, index: int):
    if index < 0:
        return total + index
    else:
        return index


class Pagination:
    def __init__(
        self,
        request: Request,
        response: Response,
        page: int = Query(0),
        per_page: int = Query(10, le=100),
    ):
        self.page = page
        self.per_page = per_page
        self._base_url = request.url
        self._response = response

    def _paginate_list(self, data: list) -> list:
        total_count = len(data)
        total_pages = ceil(total_count / self.per_page)
        page = _make_index_positive(total_pages, self.page)

        start = page * self.per_page
        end = start + self.per_page

        paginated_data = data[start:end]
        self.set_link_header(total_pages)

        return paginated_data

    def _to_peewee(self, total: int):
        page = _make_index_positive(total, self.page) + 1

        return page, self.per_page

    def paginate(self, data: list | type[peewee.Model] | Path) -> list:
        """
        Paging the data.

        This method supports two types of data paging: normal lists and Peewee model classes.
        For ordinary lists, slice directly to obtain the data of the current page;
        For the Peewee model class, use the methods it provides for database query paging.

        Parameters:
        - data: Data that needs to be paginated, which can be a list or a Peewee model class.

        Return:
        - paginated_data: The paginated data list.
        """
        if not isinstance(data, type):
            if isinstance(data, list):
                return self._paginate_list(data)
            elif isinstance(data, Path):
                return self._paginate_list(
                    data.read_text(encoding="utf-8").splitlines()
                )

        else:
            if issubclass(data, peewee.Model):
                total_items = data.select().count()
                total_pages = (total_items + self.per_page - 1) // self.per_page
                page, per_page = self._to_peewee(total_pages)
                query = data.select().paginate(page, per_page)

                self.set_link_header(total_pages)
                return list(query)

    def set_link_header(self, total_pages: int):
        self._response.headers.update(self._get_link_header(total_pages))

    def _get_link_header(self, total_pages: int):
        links = self._generate_pagination_links(total_pages)
        headers = {"Link": ", ".join(links)}
        return headers

    def _generate_pagination_links(self, total_pages: int) -> list[str]:
        base_url = self._base_url
        links = []
        if self.page > 1:
            prev_query = f"page={self.page-1}&per_page={self.per_page}"
            links.append(f'<{base_url.replace(query=prev_query)}>; rel="prev"')
        if self.page < total_pages:
            next_query = f"page={self.page+1}&per_page={self.per_page}"
            links.append(f'<{base_url.replace(query=next_query)}>; rel="next"')

        first_query = f"page=1&per_page={self.per_page}"
        last_query = f"page={total_pages}&per_page={self.per_page}"
        links.append(f'<{base_url.replace(query=first_query)}>; rel="first"')
        links.append(f'<{base_url.replace(query=last_query)}>; rel="last"')

        return links
