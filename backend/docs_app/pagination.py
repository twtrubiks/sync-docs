from django.core.paginator import Paginator, Page
from django.conf import settings


def paginate_queryset(queryset, page: int, page_size: int) -> tuple[Page, int]:
    """
    通用分頁處理：正規化參數並回傳分頁結果。

    Args:
        queryset: Django QuerySet
        page: 頁碼（<1 會被修正為 1）
        page_size: 每頁筆數（<=0 使用 DEFAULT_PAGE_SIZE，超過 MAX_PAGE_SIZE 會被截斷）

    Returns:
        (page_obj, page_size): 分頁物件和正規化後的 page_size
    """
    if page_size <= 0:
        page_size = settings.DEFAULT_PAGE_SIZE
    page_size = min(page_size, settings.MAX_PAGE_SIZE)
    page = max(1, page)

    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(page)
    return page_obj, page_size
